from __future__ import annotations

import uuid
from typing import Any

from platform_common.filters import LIKE_ESCAPE, escape_like, filter_values
from platform_common.options import OptionColumns, preview_options, search_options
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.filters import EventFilters
from app.domain.models import AuditEvent


def apply_filters[S: (Select[tuple[AuditEvent]], Select[tuple[int]])](stmt: S, filters: EventFilters) -> S:
    if filters.occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < filters.occurred_to)
    if filters.actor_id:
        stmt = stmt.where(AuditEvent.actor_id == filters.actor_id)
    names = filter_values(filters.actor_name)
    if names:
        stmt = stmt.where(
            or_(*(AuditEvent.actor_name_snapshot.like(f"%{escape_like(name)}%", escape=LIKE_ESCAPE) for name in names))
        )
    for column, value in (
        (AuditEvent.module_code, filters.module_code),
        (AuditEvent.action_code, filters.action_code),
        (AuditEvent.outcome, filters.outcome),
    ):
        values = filter_values(value)
        if values:
            stmt = stmt.where(column.in_(values))
    return stmt


async def count_events(session: AsyncSession, filters: EventFilters) -> int:
    stmt = apply_filters(select(func.count()).select_from(AuditEvent), filters)
    return int((await session.execute(stmt)).scalar_one())


async def list_events(session: AsyncSession, filters: EventFilters, *, offset: int, limit: int) -> list[AuditEvent]:
    stmt = apply_filters(select(AuditEvent), filters)
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
