from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuditEventOut
from app.application.redact import redact
from app.domain.models import AuditEvent
from app.repositories import events as event_repo


def to_out(row: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=str(row.id),
        event_id=str(row.event_id),
        occurred_at=row.occurred_at,
        received_at=row.received_at,
        source_service=row.source_service,
        schema_version=row.schema_version,
        request_id=row.request_id,
        actor_id=row.actor_id,
        actor_name_snapshot=row.actor_name_snapshot,
        module_code=row.module_code,
        action_code=row.action_code,
        target_type=row.target_type,
        target_id=row.target_id,
        outcome=row.outcome,
        error_code=row.error_code,
        client_ip=row.client_ip,
        user_agent=row.user_agent,
        changes=redact(row.changes) if row.changes is not None else None,
        summary=row.summary,
        duration_ms=row.duration_ms,
    )


async def list_page(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    actor_id: str | None,
    actor_name: str | None,
    module_code: str | None,
    action_code: str | None,
    outcome: str | None,
) -> tuple[list[AuditEventOut], int]:
    total = await event_repo.count_events(
        session,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        actor_name=actor_name,
        module_code=module_code,
        action_code=action_code,
        outcome=outcome,
    )
    rows = await event_repo.list_events(
        session,
        offset=(page - 1) * page_size,
        limit=page_size,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        actor_name=actor_name,
        module_code=module_code,
        action_code=action_code,
        outcome=outcome,
    )
    return [to_out(row) for row in rows], total


async def list_options(session: AsyncSession) -> dict[str, list[str]]:
    return await event_repo.list_options(session)


async def get_one(session: AsyncSession, event_pk: uuid.UUID) -> AuditEventOut | None:
    row = await event_repo.get_event(session, event_pk)
    return to_out(row) if row is not None else None
