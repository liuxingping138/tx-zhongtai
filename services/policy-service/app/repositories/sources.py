from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Source


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Source | None:
    return await session.get(Source, item_id)


async def get_by_internal_id(session: AsyncSession, internal_id: str) -> Source | None:
    result = await session.execute(select(Source).where(Source.internal_id == internal_id))
    return result.scalar_one_or_none()


async def get_by_site_code(session: AsyncSession, site_code: str) -> Source | None:
    result = await session.execute(select(Source).where(Source.site_code == site_code))
    return result.scalar_one_or_none()


async def list_internal_ids(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Source.internal_id))
    return set(result.scalars())


async def list_site_codes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Source.site_code))
    return set(result.scalars())


async def list_site_codes_for_district(session: AsyncSession, district_code: str) -> list[str]:
    prefix = district_code or ""
    result = await session.execute(
        select(Source.site_code)
        .where(or_(Source.district_code == prefix, Source.site_code.startswith(prefix)))
        .with_for_update()
    )
    return list(result.scalars())


async def list_items(
    session: AsyncSession,
    *,
    site_name: str | None,
    province_name: str | None,
    city_name: str | None,
    tag: str | None,
    site_code: str | None,
    crawl_priority: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Source], int]:
    stmt = select(Source)
    count_stmt = select(func.count()).select_from(Source)
    filters = [
        (Source.site_name, site_name),
        (Source.province_name, province_name),
        (Source.city_name, city_name),
        (Source.tag, tag),
        (Source.site_code, site_code),
        (Source.crawl_priority, crawl_priority),
    ]
    for column, value in filters:
        if value:
            cond = column.ilike(f"%{value}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(Source.site_code, Source.site_name).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars()), total


async def list_all(session: AsyncSession) -> list[Source]:
    result = await session.execute(select(Source).order_by(Source.site_code, Source.site_name))
    return list(result.scalars())
