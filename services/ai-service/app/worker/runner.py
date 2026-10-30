"""批量任务执行进程：持全局锁的单个 leader 从数据库队列认领任务，最多同时跑 batch_max_running 个，
其中留一个给样本试跑和定时打标。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from sqlalchemy import text

from app.application.batch_execute import execute
from app.application.batch_queue import BULK_SOURCES, beat, bulk_limit, claim_next, recover_orphans
from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger("ai.worker")
LEADER_LOCK = 72120261015
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 10.0


async def heartbeat() -> None:
    while True:
        # 库连接抖一下不能让它死掉：它一停，健康检查从此一直报不健康。
        try:
            await beat()
        except Exception:  # 下一次接着写
            logger.warning("worker_heartbeat_failed", exc_info=True)
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def _claim(running: dict[asyncio.Task[None], tuple[str, str]], limit: int) -> tuple[str, str] | None:
    """有空位才认领；页面批量任务占满它那份后，只认领样本试跑和定时打标。

    认领失败（库重启、连接被重置）只等下一轮再试：跳出循环会把在跑的任务全部取消、收尾成「中断」。
    """

    if len(running) >= limit:
        return None
    bulk = sum(1 for _, source in running.values() if source in BULK_SOURCES)
    exclude = BULK_SOURCES if bulk >= bulk_limit(limit) else ()
    # 本进程还在跑的不认领：原来认领了再跳过，任务已被改成「运行中」却没人执行，过一会儿又被判中断。
    mine = {run_id for run_id, _ in running.values()}
    try:
        return await claim_next(exclude_sources=exclude, exclude_ids=mine)
    except Exception:
        logger.warning("batch_run_claim_failed", exc_info=True)
        return None


async def consume(stop: asyncio.Event) -> None:
    recovered = await recover_orphans()
    if recovered:
        logger.warning("batch_runs_interrupted count=%s", recovered)
    limit = get_settings().batch_max_running
    running: dict[asyncio.Task[None], tuple[str, str]] = {}
    try:
        while not stop.is_set():
            running = {task: claimed for task, claimed in running.items() if not task.done()}
            claimed = await _claim(running, limit)
            if claimed:
                logger.info("batch_run_claimed run=%s source=%s", *claimed)
                running[asyncio.create_task(execute(claimed[0]))] = claimed
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
