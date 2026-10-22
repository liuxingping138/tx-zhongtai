"""单个持锁调度器，数据库持久化队列；同步继续使用各自的跨进程锁。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.aitag.application.tagging import run_batch as run_policy_tagging
from app.common.errors import UserFacingError
from app.core.database import SessionLocal, engine
from app.crawler.application.crawler_sync import run as run_crawler_sync
from app.scheduler.application.jobs import (
    abandon_running_sync,
    claim_failure,
    claim_next_run,
    latest_watermark,
    sync_result,
)
from app.scheduler.domain.models import ScheduledRun, SchedulerHeartbeat
from app.scheduler.domain.scheduling import LEADER_LOCK, MAX_ATTEMPTS, TIMEOUTS, retry_delay

logger = logging.getLogger("policy.scheduler")
POLL_SECONDS = 5
HEARTBEAT_SECONDS = 10


def fail_run(row: ScheduledRun, message: str, now: datetime) -> None:
    row.error_message = message
    if row.attempts < MAX_ATTEMPTS:
        row.status = "retrying"
        row.available_at = now + retry_delay(row.attempts)
    else:
        row.status = "failed"
        row.finished_at = now


async def recover_interrupted() -> None:
    # 只有获得全局会话锁的新 leader 才能回收；心跳超时本身不会抢走仍持锁的任务。
    async with SessionLocal() as session:
        rows = (await session.scalars(select(ScheduledRun).where(ScheduledRun.status == "running"))).all()
        for row in rows:
            result = await sync_result(session, row)
            if result and result.get("status") == "success":
                row.status, row.result, row.finished_at = "success", result, datetime.now(UTC)
            else:
                message = "执行进程中断，恢复后将继续按成功水位补齐增量"
                await abandon_running_sync(session, row, message)
                fail_run(row, message, datetime.now(UTC))
                row.result = await sync_result(session, row)
        await session.commit()


async def claim_next() -> tuple[uuid.UUID, str, uuid.UUID] | None:
    async with SessionLocal() as session:
        return await claim_next_run(session, datetime.now(UTC))


async def execute_sync(code: str, sync_id: uuid.UUID) -> None:
    if code == "policy_ai":
        await run_policy_tagging(sync_id)
        return
    # 空库不自动跑短窗口、也不自动全量回填，要求已有成功水位。
    async with SessionLocal() as session:
        if await latest_watermark(session, code) is None:
            raise RuntimeError("尚未建立同步水位，请先完成首次历史回填，再执行增量同步")
    if code == "crawler":
        await run_crawler_sync(mode="incremental", run_id=sync_id)
    else:
        raise RuntimeError("未知任务，拒绝执行")


def safe_error(exc: Exception, code: str = "crawler") -> str:
    if isinstance(exc, TimeoutError):
        minutes = int(TIMEOUTS.get(code, 1800) // 60)
        return f"执行超过 {minutes} 分钟，已中止本次执行，请检查源库连接和执行范围"
    if isinstance(exc, UserFacingError):
        return str(exc)[:300]
    # 不把连接串、SQL 参数或凭据透传到页面。
    if isinstance(exc, RuntimeError) and str(exc).startswith(("尚未建立同步水位", "已有爬虫", "未知任务")):
        return str(exc)[:300]
    return f"同步失败（{type(exc).__name__}），请检查源库连接及执行进程日志"


async def execute_claim(claim: tuple[uuid.UUID, str, uuid.UUID]) -> None:
    run_id, code, sync_id = claim
    error = None
    try:
        await asyncio.wait_for(execute_sync(code, sync_id), timeout=TIMEOUTS.get(code, 1800))
    except Exception as exc:  # noqa: BLE001  任何同步失败都要落到执行记录并按策略重试，不能让 worker 退出
        error = safe_error(exc, code)
        logger.warning("scheduled_sync_failed job=%s run=%s reason=%s", code, run_id, error)
    # CancelledError 留给进程退出后的 recover_interrupted。超时会进上面的 Exception。
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, run_id)
        if row is None:
            raise RuntimeError("执行记录丢失")
        await abandon_running_sync(session, row, error or "同步批次未成功完成")
        row.result = await sync_result(session, row)
        status = row.result.get("status") if row.result else None
        failure = claim_failure(error, status if isinstance(status, str) else None)
        if failure:
            fail_run(row, failure, datetime.now(UTC))
        else:
            row.status, row.finished_at, row.error_message = "success", datetime.now(UTC), None
        await session.commit()


async def heartbeat(connection: AsyncConnection) -> None:
    while True:
        now = datetime.now(UTC)
        await connection.execute(
            insert(SchedulerHeartbeat)
            .values(id=1, seen_at=now)
            .on_conflict_do_update(index_elements=["id"], set_={"seen_at": now})
        )
        await connection.commit()
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def consume() -> None:
    await recover_interrupted()
    while True:
        claim = await claim_next()
        if claim:
            await execute_claim(claim)
        else:
            await asyncio.sleep(POLL_SECONDS)


async def lead(stop: asyncio.Event) -> None:
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK})
        await connection.commit()
        if not locked:
            await asyncio.sleep(POLL_SECONDS)
            return
        tasks = [
            asyncio.create_task(heartbeat(connection)),
            asyncio.create_task(consume()),
            asyncio.create_task(stop.wait()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # 先停同步，再释放 leader 锁，避免新进程接管时旧任务仍继续写。
            with contextlib.suppress(Exception):
                await connection.rollback()
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
        except Exception as exc:  # noqa: BLE001  数据库或锁暂时不可用时等待后重试，调度进程常驻不退出
            logger.warning("scheduler_unavailable reason=%s", type(exc).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    await engine.dispose()
