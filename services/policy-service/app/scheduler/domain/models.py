from __future__ import annotations

from platform_common.orm_base import Base
from platform_common.scheduler.models import (
    ScheduledJobMixin,
    ScheduledRunMixin,
    SchedulerHeartbeatMixin,
    run_table_args,
)


class ScheduledJob(ScheduledJobMixin, Base):
    __tablename__ = "policy_scheduled_jobs"
    __table_args__ = {"comment": "定时同步任务配置"}


class ScheduledRun(ScheduledRunMixin, Base):
    __tablename__ = "policy_scheduled_runs"
    __jobs_table__ = "policy_scheduled_jobs"
    __table_args__ = run_table_args("定时同步执行记录")


class SchedulerHeartbeat(SchedulerHeartbeatMixin, Base):
    __tablename__ = "policy_scheduler_heartbeat"
    __table_args__ = {"comment": "调度进程心跳"}
