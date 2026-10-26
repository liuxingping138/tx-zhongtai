"""IAM 登记的定时任务。调度引擎在 platform_common.scheduler，执行在 iam-worker 里。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.scheduler import Job, Scheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.session_cleanup import cleanup_sessions
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat
from app.repositories import outbox as outbox_repo

SESSION_CLEANUP = "iam_session_cleanup"


async def run_session_cleanup(_batch: uuid.UUID) -> dict[str, Any]:
    retention_days = get_settings().session_retention_days
    async with SessionLocal() as session:
        result = await cleanup_sessions(session, retention_days=retention_days)
    return {
        "retention_days": retention_days,
        "tokens_deleted": result.tokens_deleted,
        "sessions_deleted": result.sessions_deleted,
        "tokens_remaining": result.tokens_remaining,
        "sessions_remaining": result.sessions_remaining,
    }


async def enqueue_audit(
    session: AsyncSession,
    *,
    event_type: str,
    actor: Actor,
    target_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """调度改计划、手动执行的审计，与业务同事务写进 iam_outbox。"""

    payload: dict[str, Any] = {
        "actor_id": actor.id,
        "actor_name": actor.name,
        "target_id": target_id,
        "outcome": "success",
        "changes": changes or {},
        **(extra or {}),
    }
    await outbox_repo.enqueue(session, event_type=event_type, payload=payload)


scheduler = Scheduler(
    jobs=[Job(SESSION_CLEANUP, "清理失效会话", run_session_cleanup, timeout_seconds=600)],
    job_model=ScheduledJob,
    run_model=ScheduledRun,
    heartbeat_model=SchedulerHeartbeat,
    audit=enqueue_audit,
)
