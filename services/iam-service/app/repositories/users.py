from __future__ import annotations

import uuid
from typing import Any

from platform_common.filters import FilterValue, contains_ilike, filter_values
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utcnow
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import NodeType, RoleStatus, UserStatus
from app.domain.models import Resource, Role, RoleGrant, User, UserRole


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User).where(User.username == username, User.status != UserStatus.DELETED)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_for_update(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    return result.scalar_one_or_none()


def _apply_user_filters(
    stmt: Any, *, username: FilterValue, status: FilterValue, role_id: FilterValue = None
) -> Any:
    role_ids = [_uuid_or_none(item) for item in filter_values(role_id)]
    if role_ids:
        # 选了多个角色是「或」：拥有其中任一角色即命中。非法 id 当作匹配不到，不报错。
        valid = [item for item in role_ids if item is not None]
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).where(UserRole.role_id.in_(valid))))
    names = filter_values(username)
    if names:
        stmt = stmt.where(or_(*(contains_ilike(User.username, name) for name in names)))
    # 已删除的账号不出现在列表里，筛选「禁用 / 归档」也不会把它们带出来。
    stmt = stmt.where(User.status != UserStatus.DELETED)
    statuses = [item for item in filter_values(status) if item != UserStatus.DELETED]
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))
    return stmt


async def count_users(
    session: AsyncSession, *, username: FilterValue, status: FilterValue, role_id: FilterValue = None
) -> int:
    stmt = _apply_user_filters(
        select(func.count()).select_from(User), username=username, status=status, role_id=role_id
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_users(
    session: AsyncSession,
    *,
    username: FilterValue,
    status: FilterValue,
    offset: int,
    limit: int,
    sort: str,
    role_id: FilterValue = None,
) -> list[User]:
    stmt = _apply_user_filters(select(User), username=username, status=status, role_id=role_id)
    if sort == "username":
        stmt = stmt.order_by(User.username.asc())
    else:
        stmt = stmt.order_by(User.created_at.desc())
    result = await session.execute(stmt.offset(offset).limit(limit))
    return list(result.scalars().all())


async def user_has_builtin_superadmin(session: AsyncSession, user_id: uuid.UUID) -> bool:
    stmt = (
        select(Role.id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Role.is_builtin.is_(True),
            Role.code == SUPERADMIN_ROLE_CODE,
            Role.status == "active",
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def clear_user_roles(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(UserRole).where(UserRole.user_id == user_id))


async def lock_superadmin_users(session: AsyncSession) -> list[User]:
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == SUPERADMIN_ROLE_CODE, Role.is_builtin.is_(True))
        .with_for_update()
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def list_user_role_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(select(UserRole.role_id).where(UserRole.user_id == user_id))
    return list(result.scalars().all())


async def list_user_role_names(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.status == RoleStatus.ACTIVE)
        .order_by(Role.is_builtin.desc(), Role.name)
    )
    return list(result.scalars().all())


async def replace_user_roles(
    session: AsyncSession,
    user_id: uuid.UUID,
    role_ids: list[uuid.UUID],
    *,
    granted_by: uuid.UUID,
) -> None:
    existing = await session.execute(select(UserRole).where(UserRole.user_id == user_id))
    for link in existing.scalars().all():
        await session.delete(link)
    await session.flush()
    now = utcnow()
    for role_id in role_ids:
        session.add(UserRole(user_id=user_id, role_id=role_id, granted_by=granted_by, created_at=now))


async def list_superadmin_users(session: AsyncSession) -> list[User]:
    stmt = (
        select(User)
        .options(selectinload(User.user_roles))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == SUPERADMIN_ROLE_CODE, Role.is_builtin.is_(True))
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def roles_for_users(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Role]]:
    """一次查出一页用户各自的角色，列表不必逐个请求详情。"""

    if not user_ids:
        return {}
    result = await session.execute(
        select(UserRole.user_id, Role)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(Role.is_builtin.desc(), Role.name)
    )
    out: dict[uuid.UUID, list[Role]] = {}
    for user_id, role in result.all():
        out.setdefault(user_id, []).append(role)
    return out


async def list_user_grant_sources(session: AsyncSession, user_id: uuid.UUID) -> list[tuple[str, str, Role]]:
    """用户每个角色在已发布模块上的授权，含停用角色（页面标明它不生效）。"""

    result = await session.execute(
        select(Resource.code, RoleGrant.level, Role)
        .join(RoleGrant, RoleGrant.resource_id == Resource.id)
        .join(Role, Role.id == RoleGrant.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
        .order_by(Resource.sort_order, Role.name)
    )
    return [(code, str(level), role) for code, level, role in result.all()]
