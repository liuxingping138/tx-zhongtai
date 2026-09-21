from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import BaseTag


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    return await session.get(BaseTag, item_id)


async def get_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    result = await session.execute(select(BaseTag).where(BaseTag.content_hash == digest))
    return result.scalar_one_or_none()


async def list_hashes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(BaseTag.content_hash))
    return set(result.scalars())


async def list_items(
    session: AsyncSession,
    *,
    policy_name: str | None,
    province_name: str | None,
    policy_types: str | None,
    is_penetrate: str | None,
    need_interpret: str | None,
    page: int,
    page_size: int,
) -> tuple[list[BaseTag], int]:
    stmt = select(BaseTag)
    count_stmt = select(func.count()).select_from(BaseTag)
    filters = [
        (BaseTag.policy_name, policy_name),
        (BaseTag.province_name, province_name),
        (BaseTag.policy_types, policy_types),
        (BaseTag.is_penetrate, is_penetrate),
        (BaseTag.need_interpret, need_interpret),
    ]
    for column, value in filters:
        if value:
            cond = column.ilike(f"%{value}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(BaseTag.province_code, BaseTag.policy_name).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars()), total


async def count_all(session: AsyncSession) -> int:
    """导出前先数行数，避免把超限的整表读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(BaseTag)) or 0)


async def list_all(session: AsyncSession) -> list[BaseTag]:
    result = await session.execute(select(BaseTag).order_by(BaseTag.province_code, BaseTag.policy_name))
    return list(result.scalars())
