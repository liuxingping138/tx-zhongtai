"""审计事件表。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from platform_common.orm_base import Base
from platform_common.scheduler.models import (
    ScheduledJobMixin,
    ScheduledRunMixin,
    SchedulerHeartbeatMixin,
    run_table_args,
)
from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class AuditEvent(Base):
    __tablename__ = "audit_events"
    # 索引由迁移 c2b8d4e7a201、e4b1c7d2a403 建出，必须在 model 里同步声明，
    # 否则 alembic check 会认为库里多了索引、提议把它们删掉。
    # actor_name、action_code 两个单列索引给筛选项取候选值用（repositories.events.distinct_values_stmt）。
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_actor_id", "actor_id"),
        Index("ix_audit_events_module_action", "module_code", "action_code"),
        Index("ix_audit_events_outcome", "outcome"),
        Index("ix_audit_events_actor_name", "actor_name_snapshot"),
        Index("ix_audit_events_action_code", "action_code"),
        Index("ix_audit_events_business_line", "business_line"),
        {"comment": "操作日志"},
    )

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
    # 政策 / 客户 / 招投标（policy / customer / tender），入库时算好，见 domain.business_lines；系统管理、码表管理为空。
    business_line: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="业务线")


class ScheduledJob(ScheduledJobMixin, Base):
    __tablename__ = "audit_scheduled_jobs"
    __table_args__ = {"comment": "定时任务配置"}


class ScheduledRun(ScheduledRunMixin, Base):
    __tablename__ = "audit_scheduled_runs"
    __jobs_table__ = "audit_scheduled_jobs"
    __table_args__ = run_table_args("定时任务执行记录")


class SchedulerHeartbeat(SchedulerHeartbeatMixin, Base):
    __tablename__ = "audit_scheduler_heartbeat"
    __table_args__ = {"comment": "调度进程心跳"}
