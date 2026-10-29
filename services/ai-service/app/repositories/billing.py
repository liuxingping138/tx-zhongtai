"""费用账单：批量任务（含定时打标、样本试跑）和试发、多轮对话的用量，按北京日期 × 模型 × 用途汇总。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CALL_CHAT, RUN_SOURCE_PIPELINE, RUN_SOURCE_SAMPLE, AiModel, BatchRun, CallUsage

# 页面上「用途」的写法：页面发起的统称「批量任务」，模板页的整批试跑是「样本试跑」，
# 定时任务发起的写发起方（如「政策AI打标·类型判断」）。
BATCH_PURPOSE = "批量任务"
SAMPLE_PURPOSE = "样本试跑"
CALL_PURPOSES = {CALL_CHAT: "多轮对话"}
TRIAL_PURPOSE = "试发"


def add_call(session: AsyncSession, usage: CallUsage) -> None:
    session.add(usage)


def _day(column: Any) -> Any:
    return func.date(func.timezone("Asia/Shanghai", column)).label("day")


async def daily(session: AsyncSession, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """[since, until) 之间每天、每个模型、每种用途的次数、token 和费用。批量任务按发起时间算在那一天。
    删除了的任务也算：删除只是不再列出，钱已经花出去了。

    按模型 ID 分组：任务上记的是发起当时的模型名，改过名（或旧系统导入）的同一个模型名字不一样。
    model_name 只是模型配置里已经没有这个 ID 时的备用名字。
    """

    batch_purpose = case(
        (BatchRun.source == RUN_SOURCE_PIPELINE, BatchRun.created_by_name),
        (BatchRun.source == RUN_SOURCE_SAMPLE, literal(SAMPLE_PURPOSE)),
        else_=literal(BATCH_PURPOSE),
    ).label("purpose")
    batch_day = _day(BatchRun.created_at)
    batches = (
        select(
            batch_day,
            BatchRun.model_id.label("model_id"),
            func.max(BatchRun.model_name).label("model_name"),
            batch_purpose,
            func.count().label("calls"),
            func.sum(BatchRun.input_tokens).label("input_tokens"),
            func.sum(BatchRun.output_tokens).label("output_tokens"),
            func.sum(BatchRun.inference_cost + BatchRun.search_cost).label("cost"),
        )
        .where(BatchRun.created_at >= since, BatchRun.created_at < until)
        .group_by(batch_day, BatchRun.model_id, batch_purpose)
    )
    call_purpose = case(
        *((CallUsage.kind == kind, literal(name)) for kind, name in CALL_PURPOSES.items()),
        else_=literal(TRIAL_PURPOSE),
    ).label("purpose")
    call_day = _day(CallUsage.created_at)
    calls = (
        select(
            call_day,
            CallUsage.model_id.label("model_id"),
            func.max(CallUsage.model_name).label("model_name"),
            call_purpose,
            func.count().label("calls"),
            func.sum(CallUsage.input_tokens).label("input_tokens"),
            func.sum(CallUsage.output_tokens).label("output_tokens"),
            func.sum(CallUsage.inference_cost + CallUsage.search_cost).label("cost"),
        )
        .where(CallUsage.created_at >= since, CallUsage.created_at < until)
        .group_by(call_day, CallUsage.model_id, call_purpose)
    )
    rows: list[dict[str, Any]] = []
    for statement in (batches, calls):
        rows.extend(dict(row._mapping) for row in await session.execute(statement))
    return rows


async def model_names(session: AsyncSession) -> dict[str, str]:
    """模型配置里的当前名字。模型只停用不删除，历史任务的模型基本都在。"""

    return {row.id: row.name for row in await session.execute(select(AiModel.id, AiModel.name))}
