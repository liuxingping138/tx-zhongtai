from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from platform_common.clock import assume_beijing
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.redact import redact
from app.application.schemas import AuditEventOut
from app.domain.filters import EventFilters
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
    session: AsyncSession, filters: EventFilters, *, page: int, page_size: int
) -> tuple[list[AuditEventOut], int]:
    # 页面传来的时间不带时区，按北京时间理解。
    filters = replace(
        filters,
        occurred_from=assume_beijing(filters.occurred_from),
        occurred_to=assume_beijing(filters.occurred_to),
    )
    offset = (page - 1) * page_size
    rows = await event_repo.list_events(session, filters, offset=offset, limit=page_size)
    total = await _total(session, filters, offset=offset, page_size=page_size, got=len(rows))
    return [to_out(row) for row in rows], total


async def _total(session: AsyncSession, filters: EventFilters, *, offset: int, page_size: int, got: int) -> int:
    """这页没取满就是最后一页，总数直接算出来，不再 count（按人、按时间筛常常只有一两页）。

    取满了、或者翻过了头（这页一条没有），才老老实实数一遍。
    """

    if 0 < got < page_size or (got == 0 and offset == 0):
        return offset + got
    return await event_repo.count_events(session, filters)


async def list_options(session: AsyncSession) -> dict[str, Any]:
    return await event_repo.list_options(session)


async def search_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await event_repo.search_option_values(session, field=field, keyword=keyword)


async def get_one(session: AsyncSession, event_pk: uuid.UUID) -> AuditEventOut | None:
    row = await event_repo.get_event(session, event_pk)
    return to_out(row) if row is not None else None
