from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any

from platform_common.filters import Filters, filter_values, in_any
from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_INTERRUPTED,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_SOURCE_MANUAL,
    RUN_SOURCE_PIPELINE,
    RUN_SOURCE_SAMPLE,
    RUN_STOPPING,
    BatchRun,
)

_RUNNING = (RUN_RUNNING, RUN_STOPPING)
# 批量任务列表只列正式运行（页面发起、定时任务）；样本试跑在模板页看。
TASK_SOURCES = (RUN_SOURCE_MANUAL, RUN_SOURCE_PIPELINE)


RUN_MODES = ("test", "all")


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    """同一字段多个值是「或」，不同字段之间是「且」。运行方式：测试是只跑前 N 行，全部是不限行数。"""

    conditions = [
        cond
        for cond in (
            in_any(BatchRun.prompt_title, filters.get("prompt_title")),
            in_any(BatchRun.prompt_category, filters.get("prompt_category")),
            in_any(BatchRun.created_by_name, filters.get("created_by_name")),
            in_any(BatchRun.status, filters.get("status")),
            in_any(BatchRun.source, filters.get("source")),
        )
        if cond is not None
    ]
    modes = set(filter_values(filters.get("run_mode"))) & set(RUN_MODES)
    if modes == {"test"}:
        conditions.append(BatchRun.row_limit > 0)
    elif modes == {"all"}:
        conditions.append(BatchRun.row_limit == 0)
    return conditions


async def page(
    session: AsyncSession, *, offset: int, limit: int, categories: Collection[str], filters: Filters | None = None
) -> tuple[list[BatchRun], int]:
    conditions = [
        *_conditions(filters or {}),
        BatchRun.prompt_category.in_(list(categories)),
        BatchRun.source.in_(TASK_SOURCES),
    ]
    total = int(await session.scalar(select(func.count()).select_from(BatchRun).where(*conditions)) or 0)
    rows = await session.scalars(
        select(BatchRun)
        .where(*conditions)
        .order_by(BatchRun.created_at.desc(), BatchRun.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows), total


async def distinct_values(session: AsyncSession, column: str, *, categories: Collection[str]) -> list[str]:
    field = {"prompt_title": BatchRun.prompt_title, "created_by_name": BatchRun.created_by_name}[column]
    rows = await session.scalars(
        select(field)
        .where(field != "", BatchRun.prompt_category.in_(list(categories)), BatchRun.source.in_(TASK_SOURCES))
        .distinct()
        .order_by(field)
    )
    return list(rows)


async def get(session: AsyncSession, run_id: str, *, lock: bool = False) -> BatchRun | None:
    statement = select(BatchRun).where(BatchRun.id == run_id)
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


async def active_for_prompt(
    session: AsyncSession, prompt_id: str, sources: Collection[str] = TASK_SOURCES
) -> BatchRun | None:
    """样本试跑和正式运行各管各的：试跑草稿不挡正式任务，反之亦然。"""

    statement = select(BatchRun).where(
        BatchRun.prompt_id == prompt_id, BatchRun.status.in_(ACTIVE_STATUSES), BatchRun.source.in_(list(sources))
    )
    return (await session.scalars(statement.limit(1))).first()


async def latest_samples(session: AsyncSession, prompt_ids: Collection[str]) -> dict[str, BatchRun]:
    """每个模板最近一次样本试跑。"""

    if not prompt_ids:
        return {}
    rows = await session.scalars(
        select(BatchRun)
        .where(BatchRun.prompt_id.in_(list(prompt_ids)), BatchRun.source == RUN_SOURCE_SAMPLE)
        .order_by(BatchRun.prompt_id, BatchRun.created_at.desc())
        .distinct(BatchRun.prompt_id)
    )
    return {row.prompt_id: row for row in rows}


async def sample_history(session: AsyncSession, prompt_id: str, *, limit: int) -> tuple[list[BatchRun], int]:
    """这个模板最近的几次样本试跑（新的在前）和一共试跑过几次，页面按次数叫「第 N 次」。"""

    condition = (BatchRun.prompt_id == prompt_id, BatchRun.source == RUN_SOURCE_SAMPLE)
    total = int(await session.scalar(select(func.count()).select_from(BatchRun).where(*condition)) or 0)
    rows = await session.scalars(
        select(BatchRun).where(*condition).order_by(BatchRun.created_at.desc(), BatchRun.id.desc()).limit(limit)
    )
    return list(rows), total


async def sample_runs_for_prompt(session: AsyncSession, prompt_id: str) -> list[BatchRun]:
    """这个模板自己的样本试跑记录（删模板时一起清掉）。"""

    stmt = select(BatchRun).where(BatchRun.prompt_id == prompt_id, BatchRun.source == RUN_SOURCE_SAMPLE)
    return list(await session.scalars(stmt))


def add(session: AsyncSession, run: BatchRun) -> None:
    session.add(run)


async def delete(session: AsyncSession, run: BatchRun) -> None:
    await session.delete(run)


async def mark_stale_interrupted(session: AsyncSession, *, cutoff: datetime, message: str) -> int:
    """运行中却久无心跳：执行进程已经不在了。心跳为空时按开始时间算（刚认领、还没写第一次心跳）。"""

    result = await session.execute(
        update(BatchRun)
        .where(
            BatchRun.status.in_(_RUNNING),
            or_(
                BatchRun.heartbeat_at < cutoff,
                (BatchRun.heartbeat_at.is_(None)) & (func.coalesce(BatchRun.started_at, BatchRun.created_at) < cutoff),
            ),
        )
        .values(status=RUN_INTERRUPTED, error_message=message, cancel_requested=False)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]  # UPDATE 的结果才有 rowcount，类型上看不到


async def claim_next(session: AsyncSession, *, now: datetime) -> BatchRun | None:
    """认领最早排队的任务。SKIP LOCKED：多实例时不会重复认领同一条。"""

    statement = (
        select(BatchRun)
        .where(BatchRun.status == RUN_QUEUED)
        .order_by(BatchRun.created_at, BatchRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run = (await session.scalars(statement)).first()
    if run is None:
        return None
    run.status = RUN_RUNNING
    run.started_at = now
    run.heartbeat_at = now
    return run


async def running_ids(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(BatchRun.id).where(BatchRun.status.in_(_RUNNING))))


async def update_fields(session: AsyncSession, run_id: str, values: dict[str, Any]) -> None:
    await session.execute(update(BatchRun).where(BatchRun.id == run_id).values(**values))


async def cancel_flag(session: AsyncSession, run_id: str) -> bool:
    value = await session.scalar(select(BatchRun.cancel_requested).where(BatchRun.id == run_id))
    return bool(value)
