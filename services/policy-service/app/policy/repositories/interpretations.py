from __future__ import annotations

import uuid
from collections.abc import Collection

from platform_common.filters import Filters, ilike_any, in_any
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.policy.domain.models import Interpretation, unclassified_interpretation

# 列表、导出共用的排序。最后按 ID 兜底：同名的记录每次查询先后一致，翻页不重复不漏，
# 详情页按位置取上一条、下一条也不会跳乱。
_ORDER = (Interpretation.policy_title, Interpretation.industry_scenario_code, Interpretation.id)


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Interpretation | None:
    return await session.get(Interpretation, item_id)


async def get_many_for_update(session: AsyncSession, item_ids: list[uuid.UUID]) -> list[Interpretation]:
    """批量改状态：一次锁住勾选的行，和单条编辑互斥。按主键排序加锁，避免两个批量请求交叉死锁。"""

    result = await session.execute(
        select(Interpretation).where(Interpretation.id.in_(set(item_ids))).order_by(Interpretation.id).with_for_update()
    )
    return list(result.scalars())


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> Interpretation | None:
    """更新路径专用：锁住目标行，见 sources.get_for_update 的说明。"""

    return await session.get(Interpretation, item_id, with_for_update=True)


async def get_by_relation_key(session: AsyncSession, relation_key: str) -> Interpretation | None:
    result = await session.execute(select(Interpretation).where(Interpretation.relation_key == relation_key))
    return result.scalar_one_or_none()


async def existing_relation_keys(session: AsyncSession, keys: Collection[str]) -> set[str]:
    """文件里这些关联主键哪些库里已有。按文件分片查，不把几百万行的主键整表拉进内存。"""

    found: set[str] = set()
    wanted = list(set(keys))
    for start in range(0, len(wanted), IN_CHUNK):
        chunk = wanted[start : start + IN_CHUNK]
        stmt = select(Interpretation.relation_key).where(Interpretation.relation_key.in_(chunk))
        found.update((await session.execute(stmt)).scalars())
    return found


# IN (...) 一次最多带这么多个值。
IN_CHUNK = 1000

# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "policy_title": Interpretation.policy_title,
    "industry_l1": Interpretation.industry_l1,
    "scenario_l1_name": Interpretation.scenario_l1_name,
    "opportunity_type": Interpretation.opportunity_type,
    "is_new_scenario": Interpretation.is_new_scenario,
    "new_scenario_level": Interpretation.new_scenario_level,
    "info_level": Interpretation.info_level,
    "data_status": Interpretation.data_status,
    "scenario_state": Interpretation.scenario_state,
}

# 取值有限的枚举字段用精确匹配：模糊匹配下选「一级」会把「一级场景」之类的值一并查出来。
# 一级行业、一级场景的候选值来自行业场景码表，按码表名称精确匹配，走各自的索引。
EXACT_FILTERS = frozenset(
    {
        "industry_l1",
        "scenario_l1_name",
        "is_new_scenario",
        "new_scenario_level",
        "info_level",
        "data_status",
        "scenario_state",
    }
)


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
) -> tuple[list[Interpretation], int]:
    conds = _conditions(filters)
    result = await session.execute(
        select(Interpretation).where(*conds).order_by(*_ORDER).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars())
    if len(items) < page_size and (page == 1 or items):
        return items, (page - 1) * page_size + len(items)
    total = int(await session.scalar(select(func.count()).select_from(Interpretation).where(*conds)) or 0)
    return items, total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(Interpretation).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[Interpretation]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(select(Interpretation).where(*_conditions(filters)).order_by(*_ORDER))
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[Interpretation]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


async def unclassified_rows(session: AsyncSession, limit: int) -> list[Interpretation]:
    """还没和码表比对过的行，锁住取一批；别的进程正在比对的跳过。

    只读部分索引 ix_policy_interpretations_unclassified。
    """

    result = await session.execute(
        select(Interpretation)
        .where(unclassified_interpretation())
        .order_by(Interpretation.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars())
