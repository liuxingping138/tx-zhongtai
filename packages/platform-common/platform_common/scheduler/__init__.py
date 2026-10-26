"""平台统一的每日定时任务。各服务在自己的库里建三张表、登记自己的任务，执行在本服务的 worker 里。

接入一个服务：
1. 继承 ``models`` 里的三个 mixin 建表（迁移里写好中文注释）
2. 把任务写成 ``Job`` 交给 ``Scheduler``（绑定表和本服务的审计入队）
3. HTTP 进程挂 ``build_scheduler_router``；worker 跑 ``SchedulerRunner.run``
4. 前端调度页的服务清单里加上本服务的接口前缀
"""

from platform_common.scheduler.api import JobUpdate, build_scheduler_router
from platform_common.scheduler.jobs import (
    ACTIVE,
    BEIJING,
    MAX_ATTEMPTS,
    Job,
    UserFacingError,
    claim_failure,
    fail_run,
    next_daily,
    retry_delay,
)
from platform_common.scheduler.runner import SchedulerRunner
from platform_common.scheduler.store import Scheduler

__all__ = [
    "ACTIVE",
    "BEIJING",
    "MAX_ATTEMPTS",
    "Job",
    "JobUpdate",
    "Scheduler",
    "SchedulerRunner",
    "UserFacingError",
    "build_scheduler_router",
    "claim_failure",
    "fail_run",
    "next_daily",
    "retry_delay",
]
