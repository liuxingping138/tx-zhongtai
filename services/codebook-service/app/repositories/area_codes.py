from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.filters import Filters
from app.domain.models import AreaCode


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> AreaCode | None:
    return await session.get(AreaCode, item_id)


async def get_by_county_id(session: AsyncSession, county_id: str) -> AreaCode | None:
    result = await session.execute(select(AreaCode).where(AreaCode.county_id == county_id))
    return result.scalar_one_or_none()


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "prov_name": AreaCode.prov_name,
    "city_name": AreaCode.city_name,
    "county_name": AreaCode.county_name,
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
) -> tuple[list[AreaCode], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(AreaCode).where(*conds)) or 0)
    result = await session.execute(
        select(AreaCode)
        .where(*conds)
        .order_by(AreaCode.prov_id, AreaCode.city_id, AreaCode.county_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(AreaCode).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[AreaCode]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(AreaCode).where(*_conditions(filters)).order_by(AreaCode.prov_id, AreaCode.city_id, AreaCode.county_id)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[AreaCode]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


