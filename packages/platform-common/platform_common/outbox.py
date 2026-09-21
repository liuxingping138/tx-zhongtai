"""Outbox 事件的跨服务数据结构与仓储。具体业务事件类型仍由各服务定义。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.clock import utcnow
from platform_common.enums import OutboxStatus


class OutboxEventDraft(BaseModel):
    event_type: str
    payload: dict[str, Any]
    schema_version: int = Field(default=1, ge=1)


class OutboxRepository:
    """Outbox 表的读写。

    各服务的 outbox 表结构一致、只是表名不同（policy_outbox / codebook_outbox），
    所以这里按 ORM model 参数化，逻辑只留一份。
    """

    def __init__(self, model: type[Any]) -> None:
        self._model = model

    async def enqueue(self, session: AsyncSession, *, event_type: str, payload: dict[str, Any]) -> Any:
        event = self._model(
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

    async def claim_pending(self, session: AsyncSession, *, limit: int = 20) -> list[Any]:
        model = self._model
        now = utcnow()
        result = await session.execute(
            select(model)
            .where(
                model.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
                (model.next_retry_at.is_(None)) | (model.next_retry_at <= now),
            )
            .order_by(model.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars())
        for event in events:
            event.status = OutboxStatus.DELIVERING
            event.attempts += 1
        return events

    async def mark_delivered(self, session: AsyncSession, event: Any) -> None:
        event.status = OutboxStatus.DELIVERED
        event.error_message = None
        event.next_retry_at = None

    async def mark_retry(self, session: AsyncSession, event: Any, *, error: str, max_attempts: int) -> None:
        event.error_message = error[:500]
        if event.attempts >= max_attempts:
            event.status = OutboxStatus.DEAD
            event.next_retry_at = None
            return
        event.status = OutboxStatus.FAILED
        # 指数退避，最长 60 秒。
        event.next_retry_at = utcnow() + timedelta(seconds=min(2**event.attempts, 60))
