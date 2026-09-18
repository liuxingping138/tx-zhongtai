from __future__ import annotations

import uuid

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PolicyType


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> PolicyType | None:
    return await session.get(PolicyType, item_id)


async def get_by_name(session: AsyncSession, type_name: str) -> PolicyType | None:
    result = await session.execute(select(PolicyType).where(PolicyType.type_name == type_name))
    return result.scalar_one_or_none()


async def list_items(
    session: AsyncSession,
    *,
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[PolicyType], int]:
    stmt = select(PolicyType)
    count_stmt = select(func.count()).select_from(PolicyType)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(PolicyType.type_name.ilike(like), PolicyType.definition.ilike(like), PolicyType.seq_no.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(cast(func.nullif(PolicyType.seq_no, ""), Integer), PolicyType.type_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def list_all(session: AsyncSession) -> list[PolicyType]:
    result = await session.execute(
        select(PolicyType).order_by(cast(func.nullif(PolicyType.seq_no, ""), Integer), PolicyType.type_name)
    )
    return list(result.scalars())
