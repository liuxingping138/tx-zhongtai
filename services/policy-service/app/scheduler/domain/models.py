from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from platform_common.orm_base import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class ScheduledJob(Base):
    __tablename__ = "policy_scheduled_jobs"
    __table_args__ = {"comment": "定时同步任务配置"}
    code: Mapped[str] = mapped_column(String(40), primary_key=True, comment="任务编码")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否启用每日计划")
    daily_time: Mapped[str] = mapped_column(String(5), nullable=False, comment="北京时间每日执行时刻")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="下次计划时间")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="配置版本")


class ScheduledRun(Base):
    __tablename__ = "policy_scheduled_runs"
    __table_args__ = (
        Index(
            "uq_scheduled_run_active",
            "job_code",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'retrying')"),
        ),
        Index("ix_scheduled_run_history", "job_code", "created_at"),
        {"comment": "定时同步执行记录"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="执行编号")
    job_code: Mapped[str] = mapped_column(ForeignKey("policy_scheduled_jobs.code"), nullable=False, comment="任务编码")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, comment="触发方式")
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="发起人")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="执行状态")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已尝试次数")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入队时间")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="原计划时间")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="可执行或重试时间")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="首次开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间")
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), comment="当前同步批次编号")
    error_message: Mapped[str | None] = mapped_column(Text, comment="最近一次失败原因")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, comment="同步结果摘要")


class SchedulerHeartbeat(Base):
    __tablename__ = "policy_scheduler_heartbeat"
    __table_args__ = {"comment": "调度进程心跳"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="固定记录编号")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近心跳时间")
