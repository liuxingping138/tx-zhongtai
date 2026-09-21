from __future__ import annotations

import uuid

from platform_common.filters import Filters
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.models import BaseTag


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    return await session.get(BaseTag, item_id)


async def get_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    result = await session.execute(select(BaseTag).where(BaseTag.content_hash == digest))
    return result.scalar_one_or_none()


async def list_hashes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(BaseTag.content_hash))
    return set(result.scalars())


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "policy_name": BaseTag.policy_name,
    "province_name": BaseTag.province_name,
    "policy_types": BaseTag.policy_types,
    "is_penetrate": BaseTag.is_penetrate,
    "need_interpret": BaseTag.need_interpret,
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
) -> tuple[list[BaseTag], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(BaseTag).where(*conds)) or 0)
    result = await session.execute(
        select(BaseTag)
        .where(*conds)
        .order_by(BaseTag.province_code, BaseTag.policy_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(BaseTag).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[BaseTag]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(BaseTag).where(*_conditions(filters)).order_by(BaseTag.province_code, BaseTag.policy_name)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[BaseTag]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


