"""费用账单：批量提问（含定时打标）和试发、多轮对话的用量，按北京日期 × 模型 × 用途汇总。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CALL_CHAT, RUN_SOURCE_PIPELINE, BatchRun, CallUsage

# 页面上「用途」的写法：手动的批量提问统称「批量提问」，定时任务发起的写发起方（如「政策AI打标·类型判断」）。
BATCH_PURPOSE = "批量提问"
CALL_PURPOSES = {CALL_CHAT: "多轮对话"}
TRIAL_PURPOSE = "试发"


def add_call(session: AsyncSession, usage: CallUsage) -> None:
    session.add(usage)


def _day(column: Any) -> Any:
    return func.date(func.timezone("Asia/Shanghai", column)).label("day")


async def daily(session: AsyncSession, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """[since, until) 之间每天、每个模型、每种用途的次数、token 和费用。批量任务按发起时间算在那一天。"""

    batch_purpose = case(
        (BatchRun.source == RUN_SOURCE_PIPELINE, BatchRun.created_by_name), else_=literal(BATCH_PURPOSE)
    ).label("purpose")
    batch_day = _day(BatchRun.created_at)
    batches = (
        select(
            batch_day,
            BatchRun.model_name.label("model"),
            batch_purpose,
            func.count().label("calls"),
            func.sum(BatchRun.input_tokens).label("input_tokens"),
            func.sum(BatchRun.output_tokens).label("output_tokens"),
            func.sum(BatchRun.inference_cost + BatchRun.search_cost).label("cost"),
        )
        .where(BatchRun.created_at >= since, BatchRun.created_at < until)
        .group_by(batch_day, BatchRun.model_name, batch_purpose)
    )
    call_purpose = case(
        *((CallUsage.kind == kind, literal(name)) for kind, name in CALL_PURPOSES.items()),
        else_=literal(TRIAL_PURPOSE),
    ).label("purpose")
    call_day = _day(CallUsage.created_at)
    calls = (
        select(
            call_day,
            CallUsage.model_name.label("model"),
            call_purpose,
            func.count().label("calls"),
            func.sum(CallUsage.input_tokens).label("input_tokens"),
            func.sum(CallUsage.output_tokens).label("output_tokens"),
            func.sum(CallUsage.inference_cost + CallUsage.search_cost).label("cost"),
        )
        .where(CallUsage.created_at >= since, CallUsage.created_at < until)
        .group_by(call_day, CallUsage.model_name, call_purpose)
    )
    rows: list[dict[str, Any]] = []
    for statement in (batches, calls):
        rows.extend(dict(row._mapping) for row in await session.execute(statement))
    return rows
