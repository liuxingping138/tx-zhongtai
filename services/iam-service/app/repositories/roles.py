from __future__ import annotations

import uuid
from typing import Any

from platform_common.filters import FilterValue, contains_ilike, filter_values
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.enums import NodeType
from app.domain.models import Resource, Role, RoleGrant, User, UserRole


async def get_role_by_id(session: AsyncSession, role_id: uuid.UUID) -> Role | None:
    result = await session.execute(select(Role).where(Role.id == role_id))
    return result.scalar_one_or_none()


async def get_role_by_code(session: AsyncSession, code: str) -> Role | None:
    result = await session.execute(select(Role).where(Role.code == code))
    return result.scalar_one_or_none()


async def get_role_for_update(session: AsyncSession, role_id: uuid.UUID) -> Role | None:
    result = await session.execute(select(Role).where(Role.id == role_id).with_for_update())
    return result.scalar_one_or_none()


def _apply_role_filters(stmt: Any, *, status: FilterValue, name: FilterValue = None) -> Any:
    names = filter_values(name)
    if names:
        stmt = stmt.where(or_(*(contains_ilike(Role.name, item) for item in names)))
    statuses = filter_values(status)
    if statuses:
        stmt = stmt.where(Role.status.in_(statuses))
    return stmt


async def count_roles(session: AsyncSession, *, status: FilterValue, name: FilterValue = None) -> int:
    stmt = _apply_role_filters(select(func.count()).select_from(Role), status=status, name=name)
    return int((await session.execute(stmt)).scalar_one())


async def list_roles(
    session: AsyncSession,
    *,
    status: FilterValue,
    offset: int,
    limit: int,
    name: FilterValue = None,
) -> list[Role]:
    # 内置角色固定在最前，其余按创建时间倒序，新建的角色一眼能找到。
    stmt = (
        _apply_role_filters(select(Role), status=status, name=name)
        .order_by(Role.is_builtin.desc(), Role.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_roles_by_ids(session: AsyncSession, role_ids: list[uuid.UUID]) -> list[Role]:
    if not role_ids:
        return []
    result = await session.execute(select(Role).where(Role.id.in_(role_ids)))
    return list(result.scalars().all())


async def list_role_grants(session: AsyncSession, role_id: uuid.UUID) -> list[tuple[RoleGrant, Resource]]:
    stmt = (
        select(RoleGrant, Resource)
        .join(Resource, Resource.id == RoleGrant.resource_id)
        .where(RoleGrant.role_id == role_id)
        .order_by(Resource.sort_order, Resource.code)
    )
    result = await session.execute(stmt)
    return [(grant, resource) for grant, resource in result.all()]


async def replace_role_grants(
    session: AsyncSession,
    role_id: uuid.UUID,
    grants: list[tuple[uuid.UUID, str]],
    *,
    updated_by: uuid.UUID,
) -> None:
    existing = await session.execute(select(RoleGrant).where(RoleGrant.role_id == role_id))
    for row in existing.scalars().all():
        await session.delete(row)
    await session.flush()
    now = utcnow()
    for resource_id, level in grants:
        session.add(
            RoleGrant(
                role_id=role_id,
                resource_id=resource_id,
                level=level,
                updated_by=updated_by,
                updated_at=now,
            )
        )


async def member_counts(session: AsyncSession, role_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """每个角色分给了几个人（含已禁用账号，角色列表据此提示影响范围）。"""

    if not role_ids:
        return {}
    result = await session.execute(
        select(UserRole.role_id, func.count()).where(UserRole.role_id.in_(role_ids)).group_by(UserRole.role_id)
    )
    return {role_id: int(count) for role_id, count in result.all()}


async def grant_level_counts(session: AsyncSession, role_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """每个角色在已发布模块上的只读 / 可管理数量。未发布资源不计入，免得摘要与页面对不上。"""

    if not role_ids:
        return {}
    result = await session.execute(
        select(RoleGrant.role_id, RoleGrant.level, func.count())
        .join(Resource, Resource.id == RoleGrant.resource_id)
        .where(RoleGrant.role_id.in_(role_ids), Resource.published.is_(True), Resource.node_type == NodeType.RESOURCE)
        .group_by(RoleGrant.role_id, RoleGrant.level)
    )
    out: dict[uuid.UUID, dict[str, int]] = {}
    for role_id, level, count in result.all():
        out.setdefault(role_id, {})[str(level)] = int(count)
    return out


async def list_role_members(session: AsyncSession, role_id: uuid.UUID) -> list[User]:
    result = await session.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == role_id)
        .order_by(User.status, User.username)
    )
    return list(result.scalars().all())
