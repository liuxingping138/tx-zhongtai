from __future__ import annotations

import uuid
from typing import Any, cast

from platform_common.filters import Filters
from sqlalchemy import ColumnElement, CursorResult, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

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


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "site_name": Source.site_name,
    "province_name": Source.province_name,
    "city_name": Source.city_name,
    "tag": Source.tag,
    "site_code": Source.site_code,
    "crawl_priority": Source.crawl_priority,
}


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        column = FILTER_COLUMNS[key]  # 未知字段直接报错，避免筛选被静默忽略
        if value:
            conds.append(column.ilike(f"%{value}%"))
    return conds


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[Source], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(Source).where(*conds)) or 0)
    result = await session.execute(
        select(Source)
        .where(*conds)
        .order_by(Source.site_code, Source.site_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(Source).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[Source]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(Source).where(*_conditions(filters)).order_by(Source.site_code, Source.site_name)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[Source]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


async def delete_all(session: AsyncSession) -> int:
    # execute() 的静态类型是 Result，DELETE 实际拿到的是带 rowcount 的 CursorResult。
    result = cast(CursorResult[Any], await session.execute(delete(Source)))
    return int(result.rowcount or 0)
