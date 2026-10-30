"""到期清理：只用清理账号删除，再用应用账号写入一条任务审计。"""

from __future__ import annotations

import uuid
from datetime import timedelta

from platform_common.clock import utcnow
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ingest import ingest_event
from app.application.schemas import IngestRequest
from app.domain.models import AuditEvent

# 一批删多少：一次删几十万行会长时间占着表、生成巨量 WAL；分批每批一个事务。
DELETE_BATCH = 5000


async def delete_expired(cleanup_session: AsyncSession, *, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    total = 0
    while True:
        doomed = select(AuditEvent.id).where(AuditEvent.occurred_at < cutoff).limit(DELETE_BATCH).scalar_subquery()
        result = await cleanup_session.execute(delete(AuditEvent).where(AuditEvent.id.in_(doomed)))
        await cleanup_session.commit()
        deleted = int(getattr(result, "rowcount", 0) or 0)
        total += deleted
        if deleted < DELETE_BATCH:
            return total


async def remaining_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(AuditEvent))).scalar_one())


async def record_cleanup(
    app_session: AsyncSession,
    *,
    deleted: int,
    retention_days: int,
    max_bytes: int,
) -> None:
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
