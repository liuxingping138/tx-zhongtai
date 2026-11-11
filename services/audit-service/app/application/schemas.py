from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestRequest(BaseModel):
    """内部写入体。source_service 即使传入也会被忽略，以来源凭据为准。"""

    model_config = ConfigDict(extra="ignore")

    event_id: uuid.UUID
    occurred_at: datetime
    schema_version: int = 1
    request_id: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, max_length=64)
    actor_id: str | None = Field(default=None, max_length=64)
    actor_name_snapshot: str | None = Field(default=None, max_length=128)
    module_code: str | None = Field(default=None, max_length=128)
    action_code: str | None = Field(default=None, max_length=64)
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=64)
    outcome: str = Field(min_length=1, max_length=16)
    error_code: str | None = Field(default=None, max_length=64)
    client_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=255)
    changes: dict[str, Any] | None = None
    summary: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class AuditEventOut(BaseModel):
    id: str
    event_id: str
    occurred_at: datetime
    received_at: datetime
    source_service: str
    schema_version: int
    request_id: str | None
    actor_id: str | None
    actor_name_snapshot: str | None
    module_code: str | None
    action_code: str | None
    target_type: str | None
    target_id: str | None
    outcome: str
    error_code: str | None
    client_ip: str | None
    user_agent: str | None
    changes: dict[str, Any] | None
    summary: str | None
    duration_ms: int | None
    business_line: str | None = None
