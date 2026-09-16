"""到期清理：只用清理账号删除，再用应用账号写入一条任务审计。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IngestRequest
from app.application.ingest import ingest_event
from app.core.clock import utcnow
from app.domain.models import AuditEvent


async def delete_expired(cleanup_session: AsyncSession, *, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    result = await cleanup_session.execute(
        delete(AuditEvent).where(AuditEvent.occurred_at < cutoff).returning(AuditEvent.id)
    )
    deleted = len(result.all())
    await cleanup_session.commit()
    return deleted


async def remaining_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(AuditEvent))).scalar_one())


async def record_cleanup(
    app_session: AsyncSession,
    *,
    deleted: int,
    retention_days: int,
    max_bytes: int,
) -> None:
    import uuid

    now = utcnow()
    await ingest_event(
        app_session,
        source_service="audit-service",
        body=IngestRequest(
            event_id=uuid.uuid4(),
            occurred_at=now,
            actor_name_snapshot="audit-cleanup",
            module_code="system.audit",
            action_code="cleanup",
            outcome="success",
            summary=f"清理到期审计事件 {deleted} 条，保留 {retention_days} 天",
            changes={"deleted": deleted, "retention_days": retention_days},
        ),
        max_bytes=max_bytes,
    )
