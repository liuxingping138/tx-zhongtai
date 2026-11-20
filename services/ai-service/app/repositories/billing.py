"""费用账单：批量任务（含定时打标、样本试跑）和试发、多轮对话的用量，按北京日期 × 模型 × 用途汇总。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from platform_common.clock import BEIJING
from sqlalchemy import case, delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CALL_CHAT, RUN_SOURCE_PIPELINE, RUN_SOURCE_SAMPLE, AiModel, BatchRun, CallUsage, RunCost

# 页面上「用途」的写法：页面发起的统称「批量任务」，模板页的整批试跑是「样本试跑」，
# 定时任务发起的写发起方（如「政策AI打标·类型判断」）。
BATCH_PURPOSE = "批量任务"
SAMPLE_PURPOSE = "样本试跑"
CALL_PURPOSES = {CALL_CHAT: "多轮对话（已下线）"}
TRIAL_PURPOSE = "试发"
# 业务分类：定时任务发起的是「日常调度」，其余（页面上的批量任务、样本试跑、试发、多轮对话）都算「测试」（用户定的）。
SCENE_SCHEDULED = "日常调度"
SCENE_TEST = "测试"


def add_call(session: AsyncSession, usage: CallUsage) -> None:
    session.add(usage)


_COST_COLUMNS = ("input_tokens", "output_tokens", "cached_tokens", "search_calls", "inference_cost", "search_cost")


async def add_run_costs(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    """按（任务, 日期）累加：同一天同一个任务多次写进度、重跑都加在一行上。"""

    if not rows:
        return
    statement = insert(RunCost).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["run_id", "day"],
            set_={name: getattr(RunCost, name) + getattr(statement.excluded, name) for name in _COST_COLUMNS},
        )
    )


async def drop_run_costs(session: AsyncSession, run_id: str) -> None:
    await session.execute(delete(RunCost).where(RunCost.run_id == run_id))


def _day(column: Any) -> Any:
    return func.date(func.timezone("Asia/Shanghai", column)).label("day")


async def daily(session: AsyncSession, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """[since, until) 之间每天、每个模型、每种业务分类 × 模板类型 × 用途的次数、token 和费用。
    批量任务按费用流水记在实际花钱那天（次数是那天花了钱的任务数）；没有流水的（流水表上线后才导入的旧系统任务）按发起那天算整笔。
    删除了的任务也算：删除只是不再列出，钱已经花出去了。

    按模型 ID 分组：任务上记的是发起当时的模型名，改过名（或旧系统导入）的同一个模型名字不一样。
    model_name 只是模型配置里已经没有这个 ID 时的备用名字。
    """

    batch_purpose = case(
        (BatchRun.source == RUN_SOURCE_PIPELINE, BatchRun.created_by_name),
        (BatchRun.source == RUN_SOURCE_SAMPLE, literal(SAMPLE_PURPOSE)),
        else_=literal(BATCH_PURPOSE),
    ).label("purpose")
    batch_scene = case(
        (BatchRun.source == RUN_SOURCE_PIPELINE, literal(SCENE_SCHEDULED)), else_=literal(SCENE_TEST)
    ).label("scene")
    batch_category = BatchRun.prompt_category.label("category")
    ledger_day = RunCost.day.label("day")
    booked = (
        select(
            ledger_day,
            BatchRun.model_id.label("model_id"),
            func.max(BatchRun.model_name).label("model_name"),
            batch_scene,
            batch_category,
            batch_purpose,
            func.count().label("calls"),
            func.sum(RunCost.input_tokens).label("input_tokens"),
            func.sum(RunCost.output_tokens).label("output_tokens"),
            func.sum(RunCost.cached_tokens).label("cached_tokens"),
            func.sum(RunCost.inference_cost + RunCost.search_cost).label("cost"),
        )
        .join(BatchRun, BatchRun.id == RunCost.run_id)
        .where(RunCost.day >= since.astimezone(BEIJING).date(), RunCost.day < until.astimezone(BEIJING).date())
        .group_by(ledger_day, BatchRun.model_id, batch_scene, batch_category, batch_purpose)
    )
    batch_day = _day(BatchRun.created_at)
    unbooked = (
        select(
            batch_day,
            BatchRun.model_id.label("model_id"),
            func.max(BatchRun.model_name).label("model_name"),
            batch_scene,
            batch_category,
            batch_purpose,
            func.count().label("calls"),
            func.sum(BatchRun.input_tokens).label("input_tokens"),
            func.sum(BatchRun.output_tokens).label("output_tokens"),
            func.sum(BatchRun.cached_tokens).label("cached_tokens"),
            func.sum(BatchRun.inference_cost + BatchRun.search_cost).label("cost"),
        )
        .where(
            BatchRun.created_at >= since,
            BatchRun.created_at < until,
            ~select(RunCost.run_id).where(RunCost.run_id == BatchRun.id).exists(),
            # 一分钱没花的（排队就取消、读 Excel 就失败、跑全部时整份沿用）不算一次：账单说的是「花了钱的组合」。
            (BatchRun.input_tokens + BatchRun.output_tokens + BatchRun.search_calls > 0)
            | (BatchRun.inference_cost + BatchRun.search_cost > 0),
        )
        .group_by(batch_day, BatchRun.model_id, batch_scene, batch_category, batch_purpose)
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
            literal(SCENE_TEST).label("scene"),
            CallUsage.prompt_category.label("category"),
            call_purpose,
            func.count().label("calls"),
            func.sum(CallUsage.input_tokens).label("input_tokens"),
            func.sum(CallUsage.output_tokens).label("output_tokens"),
            func.sum(CallUsage.cached_tokens).label("cached_tokens"),
            func.sum(CallUsage.inference_cost + CallUsage.search_cost).label("cost"),
        )
        .where(CallUsage.created_at >= since, CallUsage.created_at < until)
        .group_by(call_day, CallUsage.model_id, CallUsage.prompt_category, call_purpose)
    )
    rows: list[dict[str, Any]] = []
    for statement in (booked, unbooked, calls):
        rows.extend(dict(row._mapping) for row in await session.execute(statement))
    return rows


async def model_names(session: AsyncSession) -> dict[str, str]:
    """模型配置里的当前名字。模型只停用不删除，历史任务的模型基本都在。"""

    return {row.id: row.name for row in await session.execute(select(AiModel.id, AiModel.name))}
