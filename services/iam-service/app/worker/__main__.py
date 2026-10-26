from __future__ import annotations

import asyncio
import signal

import httpx
from platform_common.logging_setup import get_logger, setup_logging
from platform_common.scheduler import SchedulerRunner

from app.application import outbox_delivery
from app.application.outbox_delivery import DeliveryCounters, claim_and_deliver
from app.application.scheduled_jobs import scheduler
from app.core.config import get_settings
from app.core.database import SessionLocal, engine

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger("iam.worker")
# 与 policy 的调度锁键不同：两个服务各自一个 leader，库也各自独立。
SCHEDULER_LOCK = 72120261026
runner = SchedulerRunner(
    scheduler, engine=engine, session_factory=SessionLocal, leader_lock=SCHEDULER_LOCK, logger_name="iam.scheduler"
)


async def _log_metrics() -> None:
    async with SessionLocal() as session:
        snapshot = await outbox_delivery.metrics(session)
    logger.info(
        "outbox_metrics",
        **snapshot,
        delivered_total=DeliveryCounters.delivered,
        duplicate_total=DeliveryCounters.duplicate,
        retried_total=DeliveryCounters.retried,
        parked_total=DeliveryCounters.parked,
        lease_lost_total=DeliveryCounters.lease_lost,
    )


async def run() -> None:
    stop = asyncio.Event()

    def _stop(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())

    # 定时任务与 Outbox 投递在同一进程里并行：调度只在拿到全局锁时执行，停机时一起收尾。
    scheduling = asyncio.create_task(runner.run(stop))
    timeout = httpx.Timeout(5.0)
    cycles = 0
    async with httpx.AsyncClient(base_url=settings.audit_ingest_url.rstrip("/"), timeout=timeout) as client:
        logger.info("iam_worker_started", ingest_url=settings.audit_ingest_url)
        while not stop.is_set():
            try:
                claimed = await claim_and_deliver(settings, client)
                cycles += 1
                if cycles == 1 or cycles % 15 == 0:
                    await _log_metrics()
                if claimed == 0:
                    await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("iam_worker_loop_error")
                await asyncio.sleep(settings.worker_poll_interval_seconds)
    await scheduling
    logger.info("iam_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
