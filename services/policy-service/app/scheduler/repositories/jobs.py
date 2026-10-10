from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from platform_common.errors import NotFoundError, VersionConflictError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduler.domain.models import ScheduledJob, ScheduledRun
from app.scheduler.domain.scheduling import ACTIVE, JOBS, next_daily


async def get_job(session: AsyncSession, code: str, *, lock: bool = False) -> ScheduledJob:
    if code not in JOBS:
        raise NotFoundError("任务不存在")
    stmt = select(ScheduledJob).where(ScheduledJob.code == code)
    if lock:
        stmt = stmt.with_for_update()
    job = await session.scalar(stmt)
    if job is None:
        raise NotFoundError("任务尚未初始化，请执行数据库迁移")
    return job


async def active_run(session: AsyncSession, code: str) -> ScheduledRun | None:
    run: ScheduledRun | None = await session.scalar(
        select(ScheduledRun).where(ScheduledRun.job_code == code, ScheduledRun.status.in_(ACTIVE))
    )
    return run


async def enqueue(
    session: AsyncSession, job: ScheduledJob, now: datetime, *, trigger: str, actor_name: str
) -> ScheduledRun:
    # 调用方持有 job 行锁；唯一部分索引是第二道并发保护。
    if await active_run(session, job.code):
        raise VersionConflictError("该任务已在排队、执行或等待重试，请勿重复提交")
    row = ScheduledRun(
        job_code=job.code,
        trigger=trigger,
        actor_name=actor_name,
        status="queued",
        attempts=0,
        created_at=now,
        scheduled_at=job.next_run_at if trigger == "scheduled" else now,
        available_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def schedule_due(session: AsyncSession, now: datetime) -> None:
    jobs = (
        await session.scalars(
            select(ScheduledJob)
            .where(ScheduledJob.enabled.is_(True), ScheduledJob.next_run_at <= now)
            .order_by(ScheduledJob.code)
            .with_for_update()
        )
    ).all()
    for job in jobs:
        # 已有任务合并此次计划；积压多天只排一个增量，不逐天重复入队。
        if not await active_run(session, job.code):
            await enqueue(session, job, now, trigger="scheduled", actor_name="每日计划")
        job.next_run_at = next_daily(now, job.daily_time)


async def history(session: AsyncSession, code: str, page: int, page_size: int) -> tuple[Sequence[ScheduledRun], int]:
    where = ScheduledRun.job_code == code
    total = await session.scalar(select(func.count()).select_from(ScheduledRun).where(where)) or 0
    rows = (
        await session.scalars(
            select(ScheduledRun)
            .where(where)
            .order_by(ScheduledRun.created_at.desc(), ScheduledRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return rows, total
