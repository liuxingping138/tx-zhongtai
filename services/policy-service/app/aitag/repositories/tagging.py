from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import datetime
from decimal import Decimal

from platform_common.filters import contains_ilike
from sqlalchemy import ColumnElement, ScalarSelect, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.aitag.domain.models import PolicyAiRun, PolicyAiTask, SkippedSource
from app.aitag.domain.tasks import TASK_COST
from app.policy.domain.candidates import STATUS_PENDING, ScenarioCandidate
from app.policy.domain.models import BaseTag, Interpretation, awaiting_interpretation, awaiting_opportunity


async def task(session: AsyncSession, code: str, *, lock: bool = False) -> PolicyAiTask:
    statement = select(PolicyAiTask).where(PolicyAiTask.code == code)
    if lock:
        statement = statement.with_for_update()
    row = (await session.scalars(statement)).first()
    if row is None:
        raise RuntimeError(f"缺少政策 AI 打标任务 {code} 的设置，请先执行数据库迁移")
    return row


async def tasks(session: AsyncSession) -> dict[str, PolicyAiTask]:
    return {row.code: row for row in await session.scalars(select(PolicyAiTask))}


def _cost_column(code: str) -> InstrumentedAttribute[Decimal]:
    column: InstrumentedAttribute[Decimal] = getattr(PolicyAiRun, TASK_COST[code])
    return column


async def spent_since(session: AsyncSession, code: str, since: datetime) -> Decimal:
    """这个任务从 since 起已花的钱。按各步费用列算，旧批次的三步费用也能各归各的任务。"""

    value = await session.scalar(
        select(func.coalesce(func.sum(_cost_column(code)), 0)).where(PolicyAiRun.started_at >= since)
    )
    return Decimal(value or 0)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PolicyAiRun | None:
    return await session.get(PolicyAiRun, run_id)


async def runs_by_ids(session: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, PolicyAiRun]:
    wanted = list(dict.fromkeys(run_ids))
    if not wanted:
        return {}
    rows = await session.scalars(select(PolicyAiRun).where(PolicyAiRun.id.in_(wanted)))
    return {row.id: row for row in rows}


async def failed_ai_runs(
    session: AsyncSession, run_field: str, *, current: uuid.UUID, since: datetime, limit: int = 5
) -> list[str]:
    """这一步最近几次失败批次发起的 AI 任务（新到旧）：若紧邻的上一次在建任务阶段就失败（404 / 0 条 / 墓碑），
    调用方可继续往更早的失败批次找，沿用前面已经付费答好的行，避免 100% 重复计费。
    """

    column: InstrumentedAttribute[str] = getattr(PolicyAiRun, run_field)
    values = await session.scalars(
        select(column)
        .where(PolicyAiRun.id != current, column != "", PolicyAiRun.status == "failed", PolicyAiRun.started_at >= since)
        .order_by(PolicyAiRun.started_at.desc())
        .limit(limit)
    )
    return list(dict.fromkeys(str(value) for value in values if value))


async def failed_ai_run(session: AsyncSession, run_field: str, *, current: uuid.UUID, since: datetime) -> str:
    """兼容接口：返回最近一次失败批次发起的 AI 任务ID。"""

    found = await failed_ai_runs(session, run_field, current=current, since=since, limit=1)
    return found[0] if found else ""


async def run_of_ai_task(session: AsyncSession, run_field: str, ai_run_id: str) -> PolicyAiRun | None:
    """发起这个 AI 任务的那一批（加锁，补记费用时用）。"""

    column: InstrumentedAttribute[str] = getattr(PolicyAiRun, run_field)
    run: PolicyAiRun | None = await session.scalar(select(PolicyAiRun).where(column == ai_run_id).with_for_update())
    return run


async def base_tags_by_source(session: AsyncSession, source_ids: list[str]) -> dict[str, BaseTag]:
    if not source_ids:
        return {}
    rows = await session.scalars(
        select(BaseTag).where(BaseTag.source_content_id.in_(source_ids)).order_by(BaseTag.id).with_for_update()
    )
    return {str(row.source_content_id): row for row in rows}


async def tagged_source_ids(session: AsyncSession, source_ids: list[str]) -> set[str]:
    """这些源政策里已经打过类型标的。读取进度往回调、重读同一天时跳过它们，不再花钱问一遍。"""

    if not source_ids:
        return set()
    rows = await session.scalars(
        select(BaseTag.source_content_id).where(
            BaseTag.source_content_id.in_(source_ids), BaseTag.tagged_at.is_not(None)
        )
    )
    skipped = await session.scalars(
        select(SkippedSource.source_content_id).where(SkippedSource.source_content_id.in_(source_ids))
    )
    return {str(value) for value in rows} | {str(value) for value in skipped}


async def mark_skipped(session: AsyncSession, source_ids: list[str], reason: str, now: datetime) -> None:
    """记下问过却没写进基础标签的源政策（已记过的不动）。"""

    if not source_ids:
        return
    rows = [{"source_content_id": item, "reason": reason, "skipped_at": now} for item in dict.fromkeys(source_ids)]
    await session.execute(insert(SkippedSource).values(rows).on_conflict_do_nothing())


async def base_tags_by_hashes(session: AsyncSession, digests: Collection[str]) -> dict[str, BaseTag]:
    chunk_size = 1000
    wanted = list(dict.fromkeys(digests))
    found: dict[str, BaseTag] = {}
    for start in range(0, len(wanted), chunk_size):
        chunk = wanted[start : start + chunk_size]
        rows = await session.scalars(select(BaseTag).where(BaseTag.content_hash.in_(chunk)))
        for row in rows:
            found[row.content_hash] = row
    return found


async def interpret_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    """需要解读、还没解读过的 AI 打标政策，先打标的先解读。上一批费用到上限没做完的也在里面。"""

    rows = await session.scalars(
        select(BaseTag).where(awaiting_interpretation()).order_by(BaseTag.tagged_at, BaseTag.id).limit(limit)
    )
    return list(rows)


async def opportunity_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    rows = await session.scalars(
        select(BaseTag).where(awaiting_opportunity()).order_by(BaseTag.interpreted_at, BaseTag.id).limit(limit)
    )
    return list(rows)


async def base_tags_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, BaseTag]:
    if not ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.id.in_(ids)).order_by(BaseTag.id).with_for_update())
    return {row.id: row for row in rows}


async def interpretations_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Interpretation]:
    if not ids:
        return {}
    rows = await session.scalars(select(Interpretation).where(Interpretation.id.in_(ids)))
    return {row.id: row for row in rows}


async def ai_interpretations(session: AsyncSession, source_ids: list[str]) -> dict[str, list[Interpretation]]:
    if not source_ids:
        return {}
    rows = await session.scalars(
        select(Interpretation)
        .where(Interpretation.source_content_id.in_(source_ids))
        .order_by(Interpretation.created_at, Interpretation.id)
        .with_for_update()
    )
    grouped: dict[str, list[Interpretation]] = {}
    for row in rows:
        grouped.setdefault(str(row.source_content_id), []).append(row)
    return grouped


async def interpretations_by_source_ids(
    session: AsyncSession, source_ids: list[str]
) -> dict[str, list[Interpretation]]:
    """只读版的 ai_interpretations：页面取测试数据用，不加行锁。
    加锁的话人在页面上取 500 条样本，会和正在回填的打标、核对页的编辑互相等锁。"""

    if not source_ids:
        return {}
    rows = await session.scalars(
        select(Interpretation)
        .where(Interpretation.source_content_id.in_(source_ids))
        .order_by(Interpretation.created_at, Interpretation.id)
    )
    grouped: dict[str, list[Interpretation]] = {}
    for row in rows:
        grouped.setdefault(str(row.source_content_id), []).append(row)
    return grouped


async def taken_relation_keys(session: AsyncSession, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    return set(await session.scalars(select(Interpretation.relation_key).where(Interpretation.relation_key.in_(keys))))


async def delete_rows(session: AsyncSession, rows: list[Interpretation]) -> None:
    for row in rows:
        await session.delete(row)


async def running_runs(session: AsyncSession) -> dict[str, PolicyAiRun]:
    """每个任务正在跑的那一批（同一任务调度保证同时只有一批）。"""

    rows = await session.scalars(
        select(PolicyAiRun).where(PolicyAiRun.status == "running").order_by(PolicyAiRun.started_at)
    )
    return {row.task: row for row in rows}


async def type_retag_queue(session: AsyncSession, limit: int) -> list[BaseTag]:
    """列表上点了「重新判断类型」、还没重打的政策，先点的先打。"""

    rows = await session.scalars(
        select(BaseTag)
        .where(BaseTag.type_retag_at.is_not(None), BaseTag.source_content_id.is_not(None))
        .order_by(BaseTag.type_retag_at, BaseTag.id)
        .limit(limit)
    )
    return list(rows)


async def base_tags_by_source_ids(session: AsyncSession, source_ids: list[str]) -> list[BaseTag]:
    if not source_ids:
        return []
    return list(
        await session.scalars(select(BaseTag).where(BaseTag.source_content_id.in_(source_ids)).with_for_update())
    )


def _count(condition: ColumnElement[bool]) -> ScalarSelect[int]:
    return select(func.count()).select_from(BaseTag).where(condition).scalar_subquery()


def awaiting_similar() -> ColumnElement[bool]:
    """待找相似：新增场景审核里待审、还有解读行、还没让 AI 看过的场景。候选表只有几千行，不建部分索引。"""

    candidate = ScenarioCandidate
    return (candidate.status == STATUS_PENDING) & (candidate.row_count > 0) & candidate.ai_checked_at.is_(None)


async def scenario_backlog(session: AsyncSession, limit: int) -> list[ScenarioCandidate]:
    """政策数多的先看：影响大的场景先有 AI 的判断。"""

    rows = await session.scalars(
        select(ScenarioCandidate)
        .where(awaiting_similar())
        .order_by(ScenarioCandidate.policy_count.desc(), ScenarioCandidate.id)
        .limit(limit)
    )
    return list(rows)


async def pending_candidates(session: AsyncSession, limit: int) -> list[ScenarioCandidate]:
    """取测试数据用：待审的新增场景（AI 看没看过都算），政策数多的在前。"""

    candidate = ScenarioCandidate
    rows = await session.scalars(
        select(candidate)
        .where((candidate.status == STATUS_PENDING) & (candidate.row_count > 0))
        .order_by(candidate.policy_count.desc(), candidate.id)
        .limit(limit)
    )
    return list(rows)


async def pending_counts(session: AsyncSession) -> dict[str, int]:
    """各任务有多少待办：待重新判断类型的、待解读的、待补市场机会的、待找相似的新增场景。

    任务调度页开着时每 5 秒问一次。三个数各数各的、条件和取待办一样，每个都只读自己的部分索引；
    合成一条 count(*) FILTER 的话只能整表扫一遍，几百万行时一次就要半秒以上。
    """

    retag = BaseTag.type_retag_at.is_not(None) & BaseTag.source_content_id.is_not(None)
    row = (
        await session.execute(select(_count(retag), _count(awaiting_interpretation()), _count(awaiting_opportunity())))
    ).one()
    scenario = await session.scalar(select(func.count()).select_from(ScenarioCandidate).where(awaiting_similar()))
    return {"type": int(row[0]), "interpret": int(row[1]), "opportunity": int(row[2]), "scenario": int(scenario or 0)}


# 取测试数据是人在页面上等，查询最多跑这么久；不沿用连接上给批处理的 5 分钟。
SAMPLE_STATEMENT_TIMEOUT = "15s"


async def limit_sample_queries(session: AsyncSession) -> None:
    """这个事务里后面的查询最多跑 SAMPLE_STATEMENT_TIMEOUT（SET LOCAL，事务结束就失效，不影响连接池里的连接）。"""

    await session.execute(text(f"SET LOCAL statement_timeout = '{SAMPLE_STATEMENT_TIMEOUT}'"))


async def recent_tags(
    session: AsyncSession,
    *,
    interpreted: bool,
    limit: int,
    province: str | None = None,
    keyword: str | None = None,
    industry_l1: str | None = None,
) -> list[BaseTag]:
    """取测试/验证数据用：最近打标的要解读政策（interpreted=False），或最近解读过的政策（interpreted=True）。

    省份、一级行业按原值精确比对（各有 B 树索引，和类型判断按源库 prov_name 原样比对一致）；
    政策名称关键词按包含匹配，百分号、下划线和反斜杠按字面处理（走三元组索引）。"""

    condition = (
        BaseTag.interpreted_at.is_not(None)
        if interpreted
        else (BaseTag.need_interpret == "是") & BaseTag.source_content_id.is_not(None)
    )
    if province and province.strip():
        condition = condition & (BaseTag.province_name == province.strip())
    if keyword and keyword.strip():
        condition = condition & contains_ilike(BaseTag.policy_name, keyword.strip())
    if interpreted and industry_l1 and industry_l1.strip():
        matched_sources = select(Interpretation.source_content_id).where(
            Interpretation.source_content_id.is_not(None),
            Interpretation.industry_l1 == industry_l1.strip(),
        )
        condition = condition & BaseTag.source_content_id.in_(matched_sources)
    order = BaseTag.interpreted_at if interpreted else BaseTag.tagged_at
    rows = await session.scalars(select(BaseTag).where(condition).order_by(order.desc(), BaseTag.id).limit(limit))
    return list(rows)
