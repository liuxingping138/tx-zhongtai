from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AreaCode


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> AreaCode | None:
    return await session.get(AreaCode, item_id)


async def get_by_county_id(session: AsyncSession, county_id: str) -> AreaCode | None:
    result = await session.execute(select(AreaCode).where(AreaCode.county_id == county_id))
    return result.scalar_one_or_none()


async def list_items(
    session: AsyncSession,
    *,
    prov_name: str | None,
    city_name: str | None,
    county_name: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AreaCode], int]:
    stmt = select(AreaCode)
    count_stmt = select(func.count()).select_from(AreaCode)
    filters = [
        (AreaCode.prov_name, prov_name),
        (AreaCode.city_name, city_name),
        (AreaCode.county_name, county_name),
    ]
    for column, value in filters:
        if value:
            cond = column.ilike(f"%{value}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(AreaCode.prov_id, AreaCode.city_id, AreaCode.county_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def list_all(session: AsyncSession) -> list[AreaCode]:
    result = await session.execute(select(AreaCode).order_by(AreaCode.prov_id, AreaCode.city_id, AreaCode.county_id))
    return list(result.scalars())
