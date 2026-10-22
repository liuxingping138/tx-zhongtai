from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.aitag.domain.models import PolicyAiRun, PolicyAiTask
from app.aitag.domain.tasks import TASK_COST
from app.policy.domain.models import BaseTag, Interpretation


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


def _of_task(code: str) -> ColumnElement[bool]:
    """属于这个任务的批次：拆分后按任务列；拆分前三步合跑的旧批次，这一步花过钱也算。"""

    return or_(PolicyAiRun.task == code, _cost_column(code) > 0)


async def spent_since(session: AsyncSession, code: str, since: datetime) -> Decimal:
    """这个任务从 since 起已花的钱。按各步费用列算，旧批次的三步费用也能各归各的任务。"""

    value = await session.scalar(
        select(func.coalesce(func.sum(_cost_column(code)), 0)).where(PolicyAiRun.started_at >= since)
    )
    return Decimal(value or 0)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PolicyAiRun | None:
    return await session.get(PolicyAiRun, run_id)


async def base_tags_by_source(session: AsyncSession, source_ids: list[str]) -> dict[str, BaseTag]:
    if not source_ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.source_content_id.in_(source_ids)).with_for_update())
    return {str(row.source_content_id): row for row in rows}


async def base_tag_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    return (await session.scalars(select(BaseTag).where(BaseTag.content_hash == digest))).first()


async def interpret_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    """需要解读、还没解读过的 AI 打标政策，先打标的先解读。上一批费用到上限没做完的也在里面。"""

    rows = await session.scalars(
        select(BaseTag)
        .where(
            BaseTag.need_interpret == "是",
            BaseTag.source_content_id.is_not(None),
            BaseTag.interpreted_at.is_(None),
        )
        .order_by(BaseTag.tagged_at, BaseTag.id)
        .limit(limit)
    )
    return list(rows)


async def opportunity_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    rows = await session.scalars(
        select(BaseTag)
        .where(BaseTag.interpreted_at.is_not(None), BaseTag.opportunity_at.is_(None))
        .order_by(BaseTag.interpreted_at, BaseTag.id)
        .limit(limit)
    )
    return list(rows)


async def base_tags_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, BaseTag]:
    if not ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.id.in_(ids)).with_for_update())
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


async def daily_billing(session: AsyncSession, code: str, since: datetime) -> list[dict[str, object]]:
    """这个任务按北京时间的日期汇总：每天几批、花了多少、处理和写入多少。"""

    day = func.date(func.timezone("Asia/Shanghai", PolicyAiRun.started_at)).label("day")
    rows = await session.execute(
        select(
            day,
            func.count().label("runs"),
            func.sum(_cost_column(code)).label("cost"),
            func.sum(PolicyAiRun.source_rows).filter(PolicyAiRun.task == code).label("policies"),
            func.sum(PolicyAiRun.tagged_rows).label("tagged_rows"),
            func.sum(PolicyAiRun.interpret_rows).label("interpret_rows"),
            func.sum(PolicyAiRun.opportunity_rows).label("opportunity_rows"),
        )
        .where(PolicyAiRun.started_at >= since, _of_task(code))
        .group_by(day)
        .order_by(day.desc())
    )
    return [dict(row._mapping) for row in rows]
