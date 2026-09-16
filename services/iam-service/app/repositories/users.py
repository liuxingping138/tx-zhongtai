from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utcnow
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.models import Role, User, UserRole


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_for_update(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    return result.scalar_one_or_none()


def _apply_user_filters(stmt: Any, *, username: str | None, status: str | None) -> Any:
    if username:
        stmt = stmt.where(User.username.like(f"%{username.lower()}%"))
    if status:
        stmt = stmt.where(User.status == status)
    return stmt


async def count_users(session: AsyncSession, *, username: str | None, status: str | None) -> int:
    stmt = _apply_user_filters(select(func.count()).select_from(User), username=username, status=status)
    return int((await session.execute(stmt)).scalar_one())


async def list_users(
    session: AsyncSession,
    *,
    username: str | None,
    status: str | None,
    offset: int,
    limit: int,
    sort: str,
) -> list[User]:
    stmt = _apply_user_filters(select(User), username=username, status=status)
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
