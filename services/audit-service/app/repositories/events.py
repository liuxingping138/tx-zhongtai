from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from platform_common.filters import FilterValue, filter_values
from platform_common.options import OptionColumns, preview_options, search_options
from sqlalchemy import Select, func, or_, select
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
    actor_name: FilterValue = None,
    module_code: FilterValue = None,
    action_code: FilterValue = None,
    outcome: FilterValue = None,
):
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < occurred_to)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    names = filter_values(actor_name)
    if names:
        stmt = stmt.where(
            or_(*(AuditEvent.actor_name_snapshot.like(f"%{_escape_like(name)}%", escape="\\") for name in names))
        )
    for column, value in (
        (AuditEvent.module_code, module_code),
        (AuditEvent.action_code, action_code),
        (AuditEvent.outcome, outcome),
    ):
        values = filter_values(value)
        if values:
            stmt = stmt.where(column.in_(values))
    return stmt


async def count_events(
    session: AsyncSession,
    *,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_id: str | None = None,
    actor_name: FilterValue = None,
    module_code: FilterValue = None,
    action_code: FilterValue = None,
    outcome: FilterValue = None,
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
    actor_name: FilterValue = None,
    module_code: FilterValue = None,
    action_code: FilterValue = None,
    outcome: FilterValue = None,
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


# 筛选项字段。键名与列表接口的 query 参数一致，便于前端直接按字段名绑定。
OPTION_COLUMNS: OptionColumns = {
    "actor_name": AuditEvent.actor_name_snapshot,
    "module_code": AuditEvent.module_code,
    "action_code": AuditEvent.action_code,
}


async def list_options(session: AsyncSession) -> dict[str, Any]:
    return {"options": await preview_options(session, OPTION_COLUMNS)}


async def search_option_values(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    return await search_options(session, OPTION_COLUMNS, field=field, keyword=keyword)


async def get_event(session: AsyncSession, event_pk: uuid.UUID) -> AuditEvent | None:
    result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_pk))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    result = await session.execute(select(AuditEvent).where(AuditEvent.event_id == event_pk))
    return result.scalar_one_or_none()
