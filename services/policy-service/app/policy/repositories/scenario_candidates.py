"""新增场景候选的查询。候选表只有几千行，解读表几百万行：涉及解读表的都按 candidate_id 索引取。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from platform_common.filters import Filters, contains_ilike, filter_values, in_any
from sqlalchemy import ColumnElement, Select, distinct, exists, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.domain.candidates import STATUS_PENDING, ScenarioCandidate
from app.policy.domain.fields import SCENARIO_STATE_DUPLICATE
from app.policy.domain.models import Interpretation

C = ScenarioCandidate

# 列表筛选：页签（状态）、名称关键词、一级行业（候选下有这个行业的行）、新增级别、码表相似、政策数下限。
FILTER_KEYS = ("status", "keyword", "industry_l1", "level_label", "similar_level", "min_policies")


async def ensure(session: AsyncSession, specs: list[dict[str, Any]], now: datetime) -> dict[str, ScenarioCandidate]:
    """按 key 建好候选（已有的不动），锁住全部返回。两个进程同时写同一个新说法时靠唯一索引只建一个。"""

    if not specs:
        return {}
    values = [
        {
            "id": uuid.uuid4(),
            "status": STATUS_PENDING,
            "version": 1,
            "first_seen_at": now,
            "last_seen_at": now,
            "created_at": now,
            "updated_at": now,
            **dict.fromkeys(_TEXT_DEFAULTS, ""),
            "row_count": 0,
            "policy_count": 0,
            "industry_count": 0,
            "similar_score": 0.0,
            "decided_at": None,
            "ai_checked_at": None,
            **spec,
        }
        for spec in specs
    ]
    await session.execute(pg_insert(C).values(values).on_conflict_do_nothing(index_elements=["key"]))
    rows = await session.scalars(select(C).where(C.key.in_([spec["key"] for spec in specs])).with_for_update())
    return {row.key: row for row in rows}


_TEXT_DEFAULTS = (
    "scenario_l1",
    "scenario_l2",
    "scenario_l3",
    "industry_l1",
    "industry_l2",
    "industry_l3",
    "adopted_name",
    "target_l1",
    "target_l2",
    "target_l3",
    "reject_reason",
    "note",
    "decided_by_id",
    "decided_by_name",
    "main_industry",
    "sample_title",
    "similar_name",
    "similar_level",
    "ai_verdict",
    "ai_similar",
    "ai_target",
    "ai_reason",
)


async def get(session: AsyncSession, candidate_id: uuid.UUID) -> ScenarioCandidate | None:
    return await session.get(C, candidate_id)


async def get_for_update(session: AsyncSession, candidate_id: uuid.UUID) -> ScenarioCandidate | None:
    return await session.get(C, candidate_id, with_for_update=True)


async def by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> list[ScenarioCandidate]:
    if not ids:
        return []
    return list(await session.scalars(select(C).where(C.id.in_(ids))))


async def pending(session: AsyncSession) -> list[ScenarioCandidate]:
    """待审的候选，锁住取（重算相似场景用，几千个以内）。"""

    return list(await session.scalars(select(C).where(C.status == STATUS_PENDING).with_for_update()))


async def stats(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Any, ...]]:
    """每个候选下的行数、政策数、一级行业数、最常见的一级行业、最近一行的入库时间和政策名称。"""

    if not ids:
        return {}
    rows = await session.execute(
        select(
            Interpretation.candidate_id,
            func.count(),
            func.count(distinct(Interpretation.policy_uid)),
            func.count(distinct(Interpretation.industry_l1)),
            func.mode().within_group(Interpretation.industry_l1),
            func.max(Interpretation.created_at),
            func.array_agg(aggregate_order_by(Interpretation.policy_title, Interpretation.created_at.desc()))[1],
        )
        .where(Interpretation.candidate_id.in_(ids))
        .group_by(Interpretation.candidate_id)
    )
    return {row[0]: tuple(row[1:]) for row in rows}


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [C.row_count > 0]
    for key, value in filters.items():
        if key not in FILTER_KEYS:
            raise KeyError(key)  # 未知字段直接报错，避免筛选被静默忽略
        values = filter_values(value)
        if not values:
            continue
        if key == "keyword":
            conds.append(
                or_(
                    *(
                        contains_ilike(col, text)
                        for text in values
                        for col in (C.scenario_l1, C.scenario_l2, C.scenario_l3)
                    )
                )
            )
        elif key == "industry_l1":
            conds.append(exists().where(Interpretation.candidate_id == C.id, Interpretation.industry_l1.in_(values)))
        elif key == "min_policies":
            conds.append(C.policy_count >= int(values[0]))
        else:
            cond = in_any(getattr(C, key), values)
            if cond is not None:
                conds.append(cond)
    return conds


async def list_items(
    session: AsyncSession, *, filters: Filters, page: int, page_size: int
) -> tuple[list[ScenarioCandidate], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(C).where(*conds)) or 0)
    result = await session.scalars(
        select(C).where(*conds).order_by(C.policy_count.desc(), C.id).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result), total


async def summary(session: AsyncSession, today: datetime) -> dict[str, Any]:
    """页签上的数和一句话结论：各状态的候选数、待审涉及的行数、待审里和码表高度相似的、今天新出现的。"""

    live = C.row_count > 0
    grouped = await session.execute(select(C.status, func.count()).where(live).group_by(C.status))
    counts: dict[str, int] = {str(status): int(count) for status, count in grouped}
    pending = (C.status == STATUS_PENDING) & live
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(C.row_count), 0),
                func.count().filter(C.similar_level == "高"),
                func.count().filter(C.first_seen_at >= today),
            ).where(pending)
        )
    ).one()
    return {
        "by_status": counts,
        "pending_rows": int(row[0]),
        "pending_similar": int(row[1]),
        "new_today": int(row[2]),
    }


async def breakdown(session: AsyncSession, candidate_id: uuid.UUID, *columns: Any) -> list[tuple[Any, ...]]:
    """候选下的行按几列分组计数，多的在前：各行业几行、下级新场景各几行、AI 理由各几条。"""

    rows = await session.execute(
        select(*columns, func.count().label("n"))
        .where(Interpretation.candidate_id == candidate_id)
        .group_by(*columns)
        .order_by(func.count().desc(), *columns)
        .limit(50)
    )
    return [tuple(row) for row in rows]


def _rows_query(candidate_id: uuid.UUID, keyword: str | None) -> Select[tuple[Interpretation]]:
    query = select(Interpretation).where(Interpretation.candidate_id == candidate_id)
    if keyword:
        query = query.where(contains_ilike(Interpretation.policy_title, keyword))
    return query


async def rows_page(
    session: AsyncSession, candidate_id: uuid.UUID, *, keyword: str | None, page: int, page_size: int
) -> tuple[list[Interpretation], int]:
    query = _rows_query(candidate_id, keyword)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    result = await session.scalars(
        query.order_by(Interpretation.created_at.desc(), Interpretation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result), total


async def rows_to_apply(session: AsyncSession, candidate_id: uuid.UUID, state: str) -> list[Interpretation]:
    """候选下还没按当前决定处理的行，锁住取。标了重复的不再动。"""

    result = await session.scalars(
        select(Interpretation)
        .where(
            Interpretation.candidate_id == candidate_id,
            Interpretation.scenario_state.not_in((state, SCENARIO_STATE_DUPLICATE)),
        )
        .order_by(Interpretation.id)
        .with_for_update()
    )
    return list(result)


async def taken_relation_keys(session: AsyncSession, keys: list[str], exclude: set[uuid.UUID]) -> set[str]:
    """这些关联主键哪些已被别的行占用（不算本次要改的行自己）。"""

    taken: set[str] = set()
    wanted = list(set(keys))
    for start in range(0, len(wanted), 1000):
        chunk = wanted[start : start + 1000]
        result = await session.execute(
            select(Interpretation.id, Interpretation.relation_key).where(Interpretation.relation_key.in_(chunk))
        )
        taken.update(key for row_id, key in result if row_id not in exclude)
    return taken
