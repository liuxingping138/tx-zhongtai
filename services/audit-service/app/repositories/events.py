from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditEvent


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(
    stmt: Select[tuple[AuditEvent]] | Select[tuple[int]],
    *,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    module_code: str | None = None,
    action_code: str | None = None,
    outcome: str | None = None,
):
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < occurred_to)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if actor_name:
        stmt = stmt.where(AuditEvent.actor_name_snapshot.like(f"%{_escape_like(actor_name)}%", escape="\\"))
    if module_code:
        stmt = stmt.where(AuditEvent.module_code == module_code)
    if action_code:
        stmt = stmt.where(AuditEvent.action_code == action_code)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    return stmt


async def count_events(
    session: AsyncSession,
    *,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    module_code: str | None = None,
    action_code: str | None = None,
    outcome: str | None = None,
) -> int:
    stmt = apply_filters(
        select(func.count()).select_from(AuditEvent),
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        actor_name=actor_name,
        module_code=module_code,
        action_code=action_code,
        outcome=outcome,
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_events(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    module_code: str | None = None,
    action_code: str | None = None,
    outcome: str | None = None,
) -> list[AuditEvent]:
    stmt = apply_filters(
        select(AuditEvent),
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        actor_name=actor_name,
        module_code=module_code,
        action_code=action_code,
        outcome=outcome,
    )
    stmt = stmt.order_by(AuditEvent.occurred_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_options(session: AsyncSession) -> dict[str, list[str]]:
    async def values(column) -> list[str]:
        result = await session.execute(
            select(column).where(column.is_not(None)).where(column != "").distinct().order_by(column).limit(2000)
        )
        return [value for value in result.scalars() if value]

    return {
        "actor_name": await values(AuditEvent.actor_name_snapshot),
        "module_code": await values(AuditEvent.module_code),
        "action_code": await values(AuditEvent.action_code),
    }


async def get_event(session: AsyncSession, event_pk: uuid.UUID) -> AuditEvent | None:
    result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_pk))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    result = await session.execute(select(AuditEvent).where(AuditEvent.event_id == event_pk))
    return result.scalar_one_or_none()
