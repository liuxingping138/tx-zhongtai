"""政策服务的调度执行进程。引擎在 platform_common.scheduler；同步各自的跨进程锁仍在各领域里。"""

from __future__ import annotations

from platform_common.scheduler import SchedulerRunner

from app.common.internal_clients import close_internal_clients
from app.core.database import SessionLocal, engine
from app.scheduler.application.jobs import scheduler
from app.scheduler.domain.scheduling import LEADER_LOCK

runner = SchedulerRunner(
    scheduler, engine=engine, session_factory=SessionLocal, leader_lock=LEADER_LOCK, logger_name="policy.scheduler"
)


async def main() -> None:
    try:
        await runner.main()
    finally:
        await close_internal_clients()
