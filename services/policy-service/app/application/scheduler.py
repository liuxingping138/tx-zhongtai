from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from platform_common.actors import Actor
from platform_common.errors import VersionConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.models import CrawlerSyncRun, CrawlerV2SyncRun
from app.domain.scheduler_models import ScheduledJob, ScheduledRun, SchedulerHeartbeat
from app.domain.scheduling import JOBS, next_daily
from app.repositories import scheduler as repo


def run_data(row: ScheduledRun) -> dict[str, Any]:
    return {col.name: getattr(row, col.name) for col in ScheduledRun.__table__.columns}


async def latest_watermark(session: AsyncSession, code: str):
    model = CrawlerSyncRun if code == "crawler-v1" else CrawlerV2SyncRun
    return await session.scalar(
        select(model.watermark)
        .where(model.status == "success", model.watermark.is_not(None))
        .order_by(model.started_at.desc())
        .limit(1)
    )


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
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=code,
        changes={"before": before, "after": {"enabled": enabled, "daily_time": daily_time}},
    )


async def trigger_job(session: AsyncSession, code: str, actor: Actor) -> dict[str, Any]:
    job = await repo.get_job(session, code, lock=True)
    row = await repo.enqueue(session, job, datetime.now(UTC), trigger="manual", actor_name=actor.name)
    await enqueue_event(
        session,
        event_type="scheduler.triggered",
        actor_id=actor.id,
        actor_name=actor.name,
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
