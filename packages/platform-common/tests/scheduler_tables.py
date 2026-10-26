"""调度测试共用的三张表：用公共 mixin 建在独立的 Base 上，不连数据库。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import DeclarativeBase

from platform_common.scheduler.models import (
    ScheduledJobMixin,
    ScheduledRunMixin,
    SchedulerHeartbeatMixin,
    run_table_args,
)


class _Base(DeclarativeBase):
    pass


class JobRow(ScheduledJobMixin, _Base):
    __tablename__ = "t_scheduled_jobs"


class RunRow(ScheduledRunMixin, _Base):
    __tablename__ = "t_scheduled_runs"
    __jobs_table__ = "t_scheduled_jobs"
    __table_args__ = run_table_args("测试执行记录")


class Beat(SchedulerHeartbeatMixin, _Base):
    __tablename__ = "t_scheduler_heartbeat"


def tables() -> dict[str, Any]:
    return {"job_model": JobRow, "run_model": RunRow, "heartbeat_model": Beat}
