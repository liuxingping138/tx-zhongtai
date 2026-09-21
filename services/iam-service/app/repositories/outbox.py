"""Outbox 写入与认领。成功管理变更与本仓储同事务；失败登录等由调用方开独立事务。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from platform_common.redaction import redact
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.enums import OutboxStatus
from app.domain.models import OutboxEvent


async def enqueue(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> OutboxEvent:
    # 入队即脱敏。iam 的 payload 常带账号相关字段，而 Outbox 落在 iam_db 里、
    # 投递成功前一直存着，光靠投递时脱敏挡不住业务库留痕。
    event = OutboxEvent(
        event_id=event_id or uuid.uuid4(),
        event_type=event_type,
        schema_version=schema_version,
        payload=redact(payload),
        status=OutboxStatus.PENDING,
        attempts=0,
        created_at=utcnow(),
    )
    session.add(event)
    return event


async def enqueue_independent(
    *,
    event_type: str,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> None:
    """失败/拒绝类事件：独立事务提交，避免被业务回滚带掉。"""

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await enqueue(
            session,
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            schema_version=schema_version,
        )
        await session.commit()


async def claim_batch(
    session: AsyncSession,
    *,
    limit: int,
    lease: timedelta,
    now: datetime | None = None,
) -> list[OutboxEvent]:
    current = now or utcnow()
    expired_lease = and_(
        OutboxEvent.status == OutboxStatus.DELIVERING,
        OutboxEvent.lease_until.is_not(None),
        OutboxEvent.lease_until < current,
    )
    claimable = or_(
        OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
        expired_lease,
    )
    ready = or_(OutboxEvent.next_retry_at.is_(None), OutboxEvent.next_retry_at <= current)
    stmt = (
        select(OutboxEvent)
        .where(claimable, ready)
        .order_by(OutboxEvent.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    events = list((await session.execute(stmt)).scalars().all())
    lease_until = current + lease
    for event in events:
        event.status = OutboxStatus.DELIVERING
        event.lease_until = lease_until
        event.attempts += 1
    return events


async def mark_delivered(session: AsyncSession, event_id: uuid.UUID, expected_lease: datetime) -> bool:
    result = await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.event_id == event_id, OutboxEvent.lease_until == expected_lease)
        .values(status=OutboxStatus.DELIVERED, lease_until=None, error_message=None, next_retry_at=None)
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def mark_retry(
    session: AsyncSession,
    event_id: uuid.UUID,
    expected_lease: datetime,
    *,
    status: str,
    next_retry_at: datetime | None,
    error_message: str | None,
) -> bool:
    result = await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.event_id == event_id, OutboxEvent.lease_until == expected_lease)
        .values(
            status=status,
            lease_until=None,
            next_retry_at=next_retry_at,
            error_message=(error_message or "")[:500] or None,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def replay(
    session: AsyncSession,
    *,
    event_id: uuid.UUID | None = None,
    event_type: str | None = None,
    statuses: tuple[str, ...] = (OutboxStatus.DEAD, OutboxStatus.FAILED),
    limit: int = 200,
) -> int:
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status.in_(statuses))
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    )
    if event_id is not None:
        stmt = stmt.where(OutboxEvent.event_id == event_id)
    if event_type:
        stmt = stmt.where(OutboxEvent.event_type == event_type)
    rows = list((await session.execute(stmt)).scalars().all())
    now = utcnow()
    for event in rows:
        event.status = OutboxStatus.PENDING
        event.next_retry_at = now
        event.lease_until = None
        event.attempts = 0
        event.error_message = None
    return len(rows)


async def metrics(session: AsyncSession) -> dict[str, int | float | None]:
    counts: dict[str, int] = {}
    for status in (
        OutboxStatus.PENDING,
        OutboxStatus.DELIVERING,
        OutboxStatus.FAILED,
        OutboxStatus.DEAD,
        OutboxStatus.DELIVERED,
    ):
        value = await session.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == status))
        counts[f"{status}_count"] = int(value.scalar_one())

    oldest = await session.execute(
        select(func.min(OutboxEvent.created_at)).where(
            OutboxEvent.status.in_(
                (OutboxStatus.PENDING, OutboxStatus.FAILED, OutboxStatus.DELIVERING, OutboxStatus.DEAD)
            )
        )
    )
    oldest_at = oldest.scalar_one_or_none()
    age = None if oldest_at is None else max((utcnow() - oldest_at).total_seconds(), 0.0)
    return {**counts, "oldest_unfinished_age_seconds": age}
