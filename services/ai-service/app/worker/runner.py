"""批量任务执行进程：持全局锁的单个 leader 从数据库队列认领任务，最多同时跑 batch_max_running 个。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from sqlalchemy import text

from app.application.batch_execute import execute
from app.application.batch_queue import beat, claim_next, recover_orphans
from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger("ai.worker")
LEADER_LOCK = 72120261015
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 10.0


async def heartbeat() -> None:
    while True:
        await beat()
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def consume(stop: asyncio.Event) -> None:
    recovered = await recover_orphans()
    if recovered:
        logger.warning("batch_runs_interrupted count=%s", recovered)
    limit = get_settings().batch_max_running
    running: set[asyncio.Task[None]] = set()
    try:
        while not stop.is_set():
            running = {task for task in running if not task.done()}
            run_id = await claim_next() if len(running) < limit else None
            if run_id:
                logger.info("batch_run_claimed run=%s", run_id)
                running.add(asyncio.create_task(execute(run_id)))
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    finally:
        # 停止时取消在跑的任务：execute 会把已完成的部分收尾成「中断」再退出。
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)


async def lead(stop: asyncio.Event) -> None:
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK})
        await connection.commit()
        if not locked:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            return
        beating = asyncio.create_task(heartbeat())
        try:
            await consume(stop)
        finally:
            beating.cancel()
            await asyncio.gather(beating, return_exceptions=True)
            with contextlib.suppress(Exception):
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LEADER_LOCK})
                await connection.commit()


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    while not stop.is_set():
        try:
            await lead(stop)
        except Exception as exc:  # noqa: BLE001  数据库暂时不可用时等待后重试，执行进程常驻不退出
            logger.warning("worker_unavailable reason=%s", type(exc).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    await engine.dispose()
