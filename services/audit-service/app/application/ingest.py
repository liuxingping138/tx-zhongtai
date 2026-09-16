"""审计事件入库。提交成功后才视为接收成功；event_id 冲突视为幂等重复。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from platform_common.errors import ApiError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IngestRequest
from app.application.redact import redact
from app.core.clock import utcnow
from app.domain.models import AuditEvent
from app.repositories import events as event_repo


@dataclass(frozen=True)
class IngestResult:
    event_id: uuid.UUID
    duplicate: bool


def payload_bytes(body: IngestRequest) -> int:
    return len(body.model_dump_json().encode("utf-8"))


def build_event(source_service: str, body: IngestRequest) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        event_id=body.event_id,
        occurred_at=body.occurred_at,
        received_at=utcnow(),
        source_service=source_service,
        schema_version=body.schema_version,
        request_id=body.request_id,
        trace_id=body.trace_id,
        actor_id=body.actor_id,
        actor_name_snapshot=body.actor_name_snapshot,
        module_code=body.module_code,
        action_code=body.action_code,
        target_type=body.target_type,
        target_id=body.target_id,
        outcome=body.outcome,
        error_code=body.error_code,
        client_ip=body.client_ip,
        user_agent=body.user_agent,
        changes=redact(body.changes) if body.changes is not None else None,
        summary=body.summary,
        duration_ms=body.duration_ms,
    )


async def ingest_event(
    session: AsyncSession,
    *,
    source_service: str,
    body: IngestRequest,
    max_bytes: int,
) -> IngestResult:
    if payload_bytes(body) > max_bytes:
        raise ApiError("审计事件超过允许大小")

    session.add(build_event(source_service, body))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await event_repo.get_event(session, body.event_id)
        if existing is None:
            raise
        return IngestResult(event_id=existing.event_id, duplicate=True)
    return IngestResult(event_id=body.event_id, duplicate=False)
