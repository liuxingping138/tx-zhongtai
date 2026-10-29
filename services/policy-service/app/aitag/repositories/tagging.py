from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
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


async def spent_since(session: AsyncSession, code: str, since: datetime) -> Decimal:
    """这个任务从 since 起已花的钱。按各步费用列算，旧批次的三步费用也能各归各的任务。"""

    value = await session.scalar(
        select(func.coalesce(func.sum(_cost_column(code)), 0)).where(PolicyAiRun.started_at >= since)
    )
    return Decimal(value or 0)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PolicyAiRun | None:
    return await session.get(PolicyAiRun, run_id)


async def failed_ai_run(session: AsyncSession, run_field: str, *, current: uuid.UUID, since: datetime) -> str:
    """这一步上一次发起的 AI 任务，前提是那一批失败了（中断、超时、轮询连不上、写库出错）：
    它已经答好的行还没写进业务表，这一批重读同一批数据时可以沿用。上一批成功了就不用找，返回空串。"""

    column: InstrumentedAttribute[str] = getattr(PolicyAiRun, run_field)
    row = (
        await session.execute(
            select(PolicyAiRun.status, column)
            .where(PolicyAiRun.id != current, column != "", PolicyAiRun.started_at >= since)
            .order_by(PolicyAiRun.started_at.desc())
            .limit(1)
        )
    ).first()
    return str(row[1]) if row is not None and row[0] == "failed" else ""


async def base_tags_by_source(session: AsyncSession, source_ids: list[str]) -> dict[str, BaseTag]:
    if not source_ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.source_content_id.in_(source_ids)).with_for_update())
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
    return {str(value) for value in rows}


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


async def pending_counts(session: AsyncSession) -> dict[str, int]:
    """三个任务各有多少待办：待重新判断类型的、待解读的、待补市场机会的。"""

    retag = BaseTag.type_retag_at.is_not(None)
    interpret = (BaseTag.need_interpret == "是") & BaseTag.interpreted_at.is_(None)
    opportunity = BaseTag.interpreted_at.is_not(None) & BaseTag.opportunity_at.is_(None)
    row = (
        await session.execute(
            select(
                func.count().filter(retag),
                func.count().filter(interpret),
                func.count().filter(opportunity),
            ).where(BaseTag.source_content_id.is_not(None))
        )
    ).one()
    return {"type": int(row[0]), "interpret": int(row[1]), "opportunity": int(row[2])}


async def recent_tags(session: AsyncSession, *, interpreted: bool, limit: int) -> list[BaseTag]:
    """取测试数据用：最近打标的、要解读的政策（interpreted=False），或最近解读过的政策（interpreted=True）。"""

    condition = (
        BaseTag.interpreted_at.is_not(None)
        if interpreted
        else (BaseTag.need_interpret == "是") & BaseTag.source_content_id.is_not(None)
    )
    order = BaseTag.interpreted_at if interpreted else BaseTag.tagged_at
    rows = await session.scalars(select(BaseTag).where(condition).order_by(order.desc(), BaseTag.id).limit(limit))
    return list(rows)
