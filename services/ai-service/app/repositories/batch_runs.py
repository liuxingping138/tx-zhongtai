from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_INTERRUPTED,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_STOPPING,
    BatchRun,
)

_RUNNING = (RUN_RUNNING, RUN_STOPPING)


async def page(session: AsyncSession, *, offset: int, limit: int) -> tuple[list[BatchRun], int]:
    total = int(await session.scalar(select(func.count()).select_from(BatchRun)) or 0)
    rows = await session.scalars(
        select(BatchRun).order_by(BatchRun.created_at.desc(), BatchRun.id).offset(offset).limit(limit)
    )
    return list(rows), total


async def get(session: AsyncSession, run_id: str, *, lock: bool = False) -> BatchRun | None:
    statement = select(BatchRun).where(BatchRun.id == run_id)
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


async def active_for_prompt(session: AsyncSession, prompt_id: str) -> BatchRun | None:
    statement = select(BatchRun).where(BatchRun.prompt_id == prompt_id, BatchRun.status.in_(ACTIVE_STATUSES))
    return (await session.scalars(statement.limit(1))).first()


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
