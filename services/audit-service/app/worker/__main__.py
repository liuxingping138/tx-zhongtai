"""audit-worker：持本服务的调度锁，执行审计服务的定时任务（每天清理到期操作日志）。

只有这个进程拿到清理账号的连接串；对外提供接口的 audit-service 进程没有，被攻破也删不了日志。
"""

from __future__ import annotations

import asyncio
import signal

from platform_common.logging_setup import get_logger, setup_logging
from platform_common.scheduler import SchedulerRunner

from app.application.scheduled_jobs import scheduler
from app.core.config import get_settings
from app.core.database import SessionLocal, engine

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger("audit.worker")
# 与 IAM、政策的调度锁键不同：各服务各自一个 leader，库也各自独立。
SCHEDULER_LOCK = 72120261030
runner = SchedulerRunner(
    scheduler, engine=engine, session_factory=SessionLocal, leader_lock=SCHEDULER_LOCK, logger_name="audit.scheduler"
)


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    logger.info("audit_worker_started")
    try:
        await runner.run(stop)
    finally:
        await engine.dispose()
    logger.info("audit_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
