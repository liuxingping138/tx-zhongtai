"""审计服务登记的定时任务：每天清理到期的操作日志。调度引擎在 platform_common.scheduler，执行在 audit-worker 里。

清理要用独立的清理账号（应用账号对 audit_events 只有查和插）：清理账号的连接串只给 audit-worker，
对外提供接口的 audit-service 进程拿不到，被攻破也删不了日志。
"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.scheduler import Job, Scheduler, UserFacingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.cleanup import delete_expired, record_cleanup
from app.application.ingest import build_event
from app.application.schemas import IngestRequest
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat

AUDIT_CLEANUP = "audit_cleanup"
NO_CLEANUP_ACCOUNT = "没有配置清理账号连接（AUDIT_CLEANUP_DATABASE_URL），不能清理到期操作日志"
# 调度页上改计划、手动执行的审计：本服务就是审计库，直接写，不绕出站。
_EVENTS = {
    "scheduler.updated": ("update", "修改每日计划"),
    "scheduler.triggered": ("execute", "手动执行定时任务"),
}


async def run_cleanup(_batch: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    cleanup_url = settings.cleanup_database_url
    if not cleanup_url or cleanup_url == settings.database_url:
        raise UserFacingError(NO_CLEANUP_ACCOUNT)
    engine = create_async_engine(cleanup_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as cleanup_session:
            deleted = await delete_expired(cleanup_session, retention_days=settings.retention_days)
    finally:
        await engine.dispose()
    async with SessionLocal() as session:
        await record_cleanup(
            session, deleted=deleted, retention_days=settings.retention_days, max_bytes=settings.max_event_bytes
        )
    return {"deleted": deleted, "retention_days": settings.retention_days}


async def record_schedule_change(
    session: AsyncSession,
    *,
    event_type: str,
    actor: Actor,
    target_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    action, label = _EVENTS.get(event_type, (event_type, event_type))
    body = IngestRequest(
        event_id=uuid.uuid4(),
        occurred_at=utcnow(),
        actor_id=actor.id,
        actor_name_snapshot=actor.name,
        module_code="system.scheduler",
        action_code=action,
        target_type="scheduled_job",
        target_id=target_id,
        outcome="success",
        changes={**(changes or {}), **(extra or {})},
        summary=f"{label} / {actor.name} / {target_id}",
    )
    session.add(build_event("audit-service", body))


scheduler = Scheduler(
    jobs=[
        Job(
            AUDIT_CLEANUP,
            "清理到期操作日志",
            run_cleanup,
            timeout_seconds=1800,
            public_errors=(NO_CLEANUP_ACCOUNT,),
        )
    ],
    job_model=ScheduledJob,
    run_model=ScheduledRun,
    heartbeat_model=SchedulerHeartbeat,
    audit=record_schedule_change,
)
