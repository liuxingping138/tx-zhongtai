from __future__ import annotations

import uuid
from collections.abc import Collection

from platform_common.filters import Filters, contains_ilike, ilike_any, in_any
from sqlalchemy import ColumnElement, func, or_, select
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


# IN (...) 一次最多带这么多个值。
IN_CHUNK = 1000


async def existing_hashes(session: AsyncSession, values: Collection[str]) -> set[str]:
    """文件里这些内容哈希哪些库里已有。按文件分片查一次，不逐行查库（场景码表 8000 多行逐行查要往返上万次）。"""

    found: set[str] = set()
    wanted = list(set(values))
    for start in range(0, len(wanted), IN_CHUNK):
        chunk = wanted[start : start + IN_CHUNK]
        result = await session.execute(select(Scenario.content_hash).where(Scenario.content_hash.in_(chunk)))
        found.update(result.scalars())
    return found


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "industry_scenario_code": Scenario.industry_scenario_code,
    "industry_l1": Scenario.industry_l1,
    "scenario_tag": Scenario.scenario_tag,
    "customer_group_name": Scenario.customer_group_name,
    "is_new_scenario": Scenario.is_new_scenario,
}
# 取值固定（是 / 否）的列精确匹配，其余按关键词模糊匹配。
EXACT_FILTERS = {"is_new_scenario"}


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        column = FILTER_COLUMNS[key]  # 未知字段直接报错，避免筛选被静默忽略
        cond = in_any(column, value) if key in EXACT_FILTERS else ilike_any(column, value)
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
        # 码表按客群重复，同编码同标签的行很多：只按这两列排，翻页时先后不固定，会重复或漏行。
        .order_by(Scenario.industry_scenario_code, Scenario.scenario_tag, Scenario.id)
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
        select(Scenario)
        .where(*_conditions(filters))
        .order_by(Scenario.industry_scenario_code, Scenario.scenario_tag, Scenario.id)
    )
    return list(result.scalars())


_PATH_COLUMNS = (
    Scenario.industry_l1,
    Scenario.industry_l2,
    Scenario.industry_l3,
    Scenario.scenario_l1_name,
    Scenario.scenario_l2_name,
    Scenario.scenario_l3_name,
)


async def search_paths(
    session: AsyncSession, *, keyword: str, industry_l1: str | None, limit: int
) -> list[tuple[str, ...]]:
    """六级名称里包含关键词的行业场景路径，按客群去重。给页面上选场景用，码表只有几千条路径，不建索引。"""

    conds = [or_(*(contains_ilike(column, keyword) for column in _PATH_COLUMNS))]
    if industry_l1:
        conds.append(Scenario.industry_l1 == industry_l1)
    result = await session.execute(
        select(Scenario.industry_scenario_code, *_PATH_COLUMNS)
        .where(*conds)
        .distinct()
        .order_by(Scenario.industry_scenario_code, *_PATH_COLUMNS)
        .limit(limit)
    )
    return [tuple(str(value or "") for value in row) for row in result]


async def list_all(session: AsyncSession) -> list[Scenario]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})
