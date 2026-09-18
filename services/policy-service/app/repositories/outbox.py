from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.enums import OutboxStatus
from app.domain.models import OutboxEvent


async def enqueue(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        schema_version=1,
        payload=payload,
        status=OutboxStatus.PENDING,
        attempts=0,
        created_at=utcnow(),
    )
    session.add(event)
    return event


async def claim_pending(session: AsyncSession, *, limit: int = 20) -> list[OutboxEvent]:
    now = utcnow()
    result = await session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
            (OutboxEvent.next_retry_at.is_(None)) | (OutboxEvent.next_retry_at <= now),
        )
        .order_by(OutboxEvent.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars())
    for event in events:
        event.status = OutboxStatus.DELIVERING
        event.attempts += 1
    return events


async def mark_delivered(session: AsyncSession, event: OutboxEvent) -> None:
    event.status = OutboxStatus.DELIVERED
    event.error_message = None
    event.next_retry_at = None


async def mark_retry(session: AsyncSession, event: OutboxEvent, *, error: str, max_attempts: int) -> None:
    event.error_message = error[:500]
    if event.attempts >= max_attempts:
        event.status = OutboxStatus.DEAD
        event.next_retry_at = None
        return
    event.status = OutboxStatus.FAILED
    event.next_retry_at = utcnow() + timedelta(seconds=min(2 ** event.attempts, 60))
