"""批量任务执行进程：持全局锁的单个 leader 从数据库队列认领任务，最多同时跑 batch_max_running 个，
其中留一个给样本试跑和定时打标。"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import signal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.application.batch_execute import execute
from app.application.batch_queue import BULK_SOURCES, beat, bulk_limit, claim_next, recover_orphans
from app.application.retention import prune_expired_runs
from app.core.codebook import close_codebook_client
from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger("ai.worker")
LEADER_LOCK = 72120261015
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 10.0
PRUNE_INTERVAL_SECONDS = 3600.0
SHUTDOWN_GRACE_SECONDS = 25.0


async def heartbeat(lock_connection: AsyncConnection) -> None:
    while True:
        # 先确认持锁连接仍然活着（断连时 Postgres 会自动释放会话锁，必须立刻退出以免双 worker 并发）。
        await lock_connection.scalar(text("SELECT 1"))
        await lock_connection.commit()
        # 写心跳库抖一下不能让 leader 退出，但连续报错会靠下一轮锁探活校验。
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


def _log_task_exception(run_id: str, task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("batch_run_task_crashed run=%s", run_id, exc_info=exc)


async def prune_loop(stop: asyncio.Event) -> None:
    """按小时清理超期的流水线和样本试跑目录，失败不打断任务执行。"""

    while not stop.is_set():
        try:
            pruned = await prune_expired_runs()
            if pruned:
                logger.info("disk_retention_pruned count=%s", pruned)
        except Exception:  # 磁盘清理失败不影响任务执行
            logger.warning("disk_retention_prune_failed", exc_info=True)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=PRUNE_INTERVAL_SECONDS)


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
                task = asyncio.create_task(execute(claimed[0], shutdown=stop))
                task.add_done_callback(functools.partial(_log_task_exception, claimed[0]))
                running[task] = claimed
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    finally:
        # 优雅停机（SIGTERM）先给在途行留出落账收尾窗口；超时或失锁取消时再强制取消。
        active = [task for task in running if not task.done()]
        if active:
            if stop.is_set():
                _, still_running = await asyncio.wait(active, timeout=SHUTDOWN_GRACE_SECONDS)
            else:
                still_running = set(active)
            for task in still_running:
                task.cancel()
            if still_running:
                await asyncio.gather(*still_running, return_exceptions=True)


async def lead(stop: asyncio.Event) -> None:
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK})
        await connection.commit()
        if not locked:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            return
        tasks = [
            asyncio.create_task(heartbeat(connection)),
            asyncio.create_task(consume(stop)),
            asyncio.create_task(prune_loop(stop)),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with contextlib.suppress(Exception):
                await connection.rollback()
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LEADER_LOCK})
                await connection.commit()


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        while not stop.is_set():
            try:
                await lead(stop)
            except Exception as exc:  # noqa: BLE001  数据库暂时不可用时等待后重试，执行进程常驻不退出
                logger.warning("worker_unavailable reason=%s", type(exc).__name__)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    finally:
        await close_codebook_client()
        await engine.dispose()
