from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.models import Resource, Role, RoleGrant


async def get_role_by_id(session: AsyncSession, role_id: uuid.UUID) -> Role | None:
    result = await session.execute(select(Role).where(Role.id == role_id))
    return result.scalar_one_or_none()


async def get_role_by_code(session: AsyncSession, code: str) -> Role | None:
    result = await session.execute(select(Role).where(Role.code == code))
    return result.scalar_one_or_none()


async def get_role_for_update(session: AsyncSession, role_id: uuid.UUID) -> Role | None:
    result = await session.execute(select(Role).where(Role.id == role_id).with_for_update())
    return result.scalar_one_or_none()


def _apply_role_filters(stmt: Any, *, status: str | None) -> Any:
    if status:
        stmt = stmt.where(Role.status == status)
    return stmt


async def count_roles(session: AsyncSession, *, status: str | None) -> int:
    stmt = _apply_role_filters(select(func.count()).select_from(Role), status=status)
    return int((await session.execute(stmt)).scalar_one())


async def list_roles(
    session: AsyncSession,
    *,
    status: str | None,
    offset: int,
    limit: int,
) -> list[Role]:
    stmt = _apply_role_filters(select(Role), status=status).order_by(Role.created_at.desc()).offset(offset).limit(limit)
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
