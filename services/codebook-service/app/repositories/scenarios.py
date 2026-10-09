from __future__ import annotations

import uuid

from platform_common.filters import Filters, ilike_any
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.models import Scenario


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Scenario | None:
    return await session.get(Scenario, item_id)


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> Scenario | None:
    """更新路径专用：锁住目标行，见 policy_types.get_for_update 的说明。"""

    return await session.get(Scenario, item_id, with_for_update=True)


async def get_by_hash(session: AsyncSession, digest: str) -> Scenario | None:
    result = await session.execute(select(Scenario).where(Scenario.content_hash == digest))
    return result.scalar_one_or_none()


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "industry_scenario_code": Scenario.industry_scenario_code,
    "industry_l1": Scenario.industry_l1,
    "scenario_tag": Scenario.scenario_tag,
    "customer_group_name": Scenario.customer_group_name,
}


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        column = FILTER_COLUMNS[key]  # 未知字段直接报错，避免筛选被静默忽略
        cond = ilike_any(column, value)
        if cond is not None:
            conds.append(cond)
    return conds


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[Scenario], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(Scenario).where(*conds)) or 0)
    result = await session.execute(
        select(Scenario)
        .where(*conds)
        .order_by(Scenario.industry_scenario_code, Scenario.scenario_tag)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(Scenario).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[Scenario]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(Scenario).where(*_conditions(filters)).order_by(Scenario.industry_scenario_code, Scenario.scenario_tag)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[Scenario]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})
