from __future__ import annotations

import asyncio
import signal

import httpx
from platform_common.logging_setup import get_logger, setup_logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.repositories import outbox as outbox_repo
from app.worker.deliver import DeliveryCounters, claim_and_deliver

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger("iam.worker")


async def _log_metrics() -> None:
    async with SessionLocal() as session:
        snapshot = await outbox_repo.metrics(session)
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
    logger.info("iam_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
