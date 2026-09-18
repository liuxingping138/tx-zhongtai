"""审计事件表。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm_base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = {"comment": "操作日志"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="主键")
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False, comment="业务事件ID")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="发生时间")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="接收时间")
    source_service: Mapped[str] = mapped_column(String(64), nullable=False, comment="来源服务")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="事件结构版本")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="链路追踪ID")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="请求ID")
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="操作人ID")
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="操作人姓名")
    module_code: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="模块编码")
    action_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="动作编码")
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="对象类型")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="对象ID")
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, comment="结果")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="错误码")
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="客户端IP")
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="浏览器标识")
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="变更内容")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="摘要")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="耗时毫秒")
