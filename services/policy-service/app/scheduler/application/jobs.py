from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from platform_common.actors import Actor
from platform_common.errors import VersionConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.crawler.domain.models import CrawlerSyncRun, CrawlerV2SyncRun
from app.scheduler.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat
from app.scheduler.domain.scheduling import JOBS, next_daily
from app.scheduler.repositories import jobs as repo


def run_data(row: ScheduledRun) -> dict[str, Any]:
    return {col.name: getattr(row, col.name) for col in ScheduledRun.__table__.columns}


async def latest_watermark(session: AsyncSession, code: str) -> datetime | None:
    model = CrawlerSyncRun if code == "crawler-v1" else CrawlerV2SyncRun
    watermark: datetime | None = await session.scalar(
        select(model.watermark)
        .where(model.status == "success", model.watermark.is_not(None))
        .order_by(model.started_at.desc())
        .limit(1)
    )
    return watermark


def claim_failure(error: str | None, sync_status: str | None) -> str | None:
    """调度成功只认底层同步批次已经写成 success。超时或中断不能记成成功。"""

    if error:
        return error
    if sync_status == "success":
        return None
    return "同步批次未成功完成"


async def abandon_running_sync(session: AsyncSession, row: ScheduledRun, message: str) -> None:
    """超时或进程中断时，把仍停在 running 的同步批次收成失败。

    ``wait_for`` 取消任务只会抛出 CancelledError，同步自己的 ``except Exception``
    接不住，批次会永远停在 running。这里在调度事务里收口。
    """

    if row.sync_run_id is None:
        return
    sync: CrawlerSyncRun | CrawlerV2SyncRun | None
    if row.job_code == "crawler-v1":
        sync = await session.get(CrawlerSyncRun, row.sync_run_id)
    else:
        sync = await session.get(CrawlerV2SyncRun, row.sync_run_id)
    if sync is None or sync.status != "running":
        return
    sync.status = "failed"
    sync.error_message = message[:2000]
    sync.finished_at = datetime.now(UTC)


async def sync_result(session: AsyncSession, row: ScheduledRun) -> dict[str, Any] | None:
    model = CrawlerSyncRun if row.job_code == "crawler-v1" else CrawlerV2SyncRun
    sync = await session.get(model, row.sync_run_id) if row.sync_run_id else None
    if sync is None:
        return row.result
    fields = ["date_from", "date_to", "watermark", "status"]
    fields += (
        ["task_rows", "stat_rows", "health_rows"] if row.job_code == "crawler-v1" else ["days_synced", "site_rows"]
    )
    return {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key in fields
        if (value := getattr(sync, key)) is not None
    }


async def list_jobs(session: AsyncSession) -> dict[str, Any]:
    heartbeat = await session.get(SchedulerHeartbeat, 1)
    now = datetime.now(UTC)
    jobs = (await session.scalars(select(ScheduledJob).order_by(ScheduledJob.code))).all()
    items = []
    for job in jobs:
        last = await session.scalar(
            select(ScheduledRun)
            .where(ScheduledRun.job_code == job.code)
            .order_by(ScheduledRun.created_at.desc())
            .limit(1)
        )
        active = await repo.active_run(session, job.code)
        items.append(
            {
                "code": job.code,
                "name": JOBS[job.code],
                "enabled": job.enabled,
                "daily_time": job.daily_time,
                "next_run_at": job.next_run_at if job.enabled else None,
                "version": job.version,
                "watermark": await latest_watermark(session, job.code),
                "active_run": run_data(active) if active else None,
                "last_run": run_data(last) if last else None,
            }
        )
    return {
        "items": items,
        "timezone": "Asia/Shanghai",
        "worker_online": bool(heartbeat and now - heartbeat.seen_at < timedelta(seconds=60)),
        "heartbeat_at": heartbeat.seen_at if heartbeat else None,
    }


async def update_job(
    session: AsyncSession, code: str, actor: Actor, *, enabled: bool, daily_time: str, version: int
) -> None:
    job = await repo.get_job(session, code, lock=True)
    if version != job.version:
        raise VersionConflictError("计划已被其他人修改，请刷新后重新设置")
    before = {"enabled": job.enabled, "daily_time": job.daily_time}
    # 停用取消尚未开始和等待重试的请求；已在执行的批次完成当前增量。
    active = await repo.active_run(session, code)
    if not enabled and active and active.status in {"queued", "retrying"}:
        active.status = "cancelled"
        active.finished_at = datetime.now(UTC)
        active.error_message = "每日计划停用，待执行请求已取消"
    if daily_time != job.daily_time or enabled != job.enabled:
        job.next_run_at = next_daily(datetime.now(UTC), daily_time)
    job.enabled = enabled
    job.daily_time = daily_time
    job.version += 1
    await enqueue_event(
        session,
        event_type="scheduler.updated",
        actor=actor,
        target_id=code,
        changes={"before": before, "after": {"enabled": enabled, "daily_time": daily_time}},
    )


async def trigger_job(session: AsyncSession, code: str, actor: Actor) -> dict[str, Any]:
    job = await repo.get_job(session, code, lock=True)
    row = await repo.enqueue(session, job, datetime.now(UTC), trigger="manual", actor_name=actor.name)
    await enqueue_event(
        session,
        event_type="scheduler.triggered",
        actor=actor,
        target_id=code,
        extra={"run_id": str(row.id)},
    )
    return run_data(row)


async def history(session: AsyncSession, code: str, page: int, page_size: int) -> dict[str, Any]:
    await repo.get_job(session, code)
    rows, total = await repo.history(session, code, page, page_size)
    items = []
    for row in rows:
        data = run_data(row)
        data["result"] = await sync_result(session, row)
        items.append(data)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def claim_next_run(session: AsyncSession, now: datetime) -> tuple[uuid.UUID, str, uuid.UUID] | None:
    """把到点的计划入队，再领取一条可执行的任务置为 running；没有可执行的返回 None。"""

    await repo.schedule_due(session, now)
    await session.commit()
    candidate = await session.scalar(
        select(ScheduledRun.job_code)
        .where(ScheduledRun.status.in_(("queued", "retrying")), ScheduledRun.available_at <= now)
        .order_by(ScheduledRun.available_at, ScheduledRun.created_at)
        .limit(1)
    )
    if candidate is None:
        return None
    # 与页面停用/入队使用相同的锁顺序：job -> run。
    await repo.get_job(session, candidate, lock=True)
    row = await repo.active_run(session, candidate)
    if row is None or row.status not in {"queued", "retrying"} or row.available_at > now:
        return None
    row.status = "running"
    row.started_at = row.started_at or now
    row.attempts += 1
    row.sync_run_id = uuid.uuid4()
    await session.commit()
    return row.id, row.job_code, row.sync_run_id
