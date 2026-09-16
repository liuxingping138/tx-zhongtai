"""Outbox 事件的跨服务数据结构。不含具体业务事件类型，也不含 ORM。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OutboxEventDraft(BaseModel):
    event_type: str
    payload: dict[str, Any]
    schema_version: int = Field(default=1, ge=1)
