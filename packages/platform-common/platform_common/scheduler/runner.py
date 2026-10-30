"""调度执行进程：持 PostgreSQL 会话锁的单 leader，按执行通道轮询数据库队列执行。

- 同一服务起几个执行进程都只有拿到锁的那个在跑；锁随连接走，进程死了自动释放
- 每条通道（Job.lane）同一时刻只跑一条，通道之间并行：几个小时的 AI 打标不堵几秒就完的同步
- 新 leader 先回收停在 running 的记录：批次其实已成功的记成功，否则收成失败按次数重试
- 每条执行按任务的超时中止；失败原因只显示能给人看的部分
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from platform_common.scheduler.jobs import DEFAULT_TIMEOUT, SHORT_LANE, UserFacingError, claim_failure, fail_run
from platform_common.scheduler.store import ONLINE_WITHIN, Scheduler

POLL_SECONDS = 5
HEARTBEAT_SECONDS = 10


class SchedulerRunner:
    def __init__(
        self,
        scheduler: Scheduler,
        *,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        leader_lock: int,
        logger_name: str,
    ) -> None:
        self.scheduler = scheduler
        self.engine = engine
        self.session_factory = session_factory
        self.leader_lock = leader_lock
        self.logger = logging.getLogger(logger_name)

    async def recover_interrupted(self, lane: str | None = None) -> None:
        """回收停在 running 的记录。lane 为空是 leader 刚接手时的全部回收（含已下线任务的记录）；
        给了通道只回收这条通道的：只在它空闲时调用，这时它名下的 running 都没人在执行。"""

        # 只有获得全局会话锁的 leader 才能回收；心跳超时本身不会抢走仍持锁的任务。
        s = self.scheduler
        run = s.run_model
        where = [run.status == "running"]
        if lane is not None:
            where.append(run.job_code.in_(s.lane_codes(lane)))
        async with self.session_factory() as session:
            rows = (await session.scalars(select(run).where(*where))).all()
            for row in rows:
                result = await s.result_of(session, row)
                job = s.jobs.get(row.job_code)
                done = result.get("status") == "success" if job and job.summary and result else False
                if done:
                    row.status, row.result, row.finished_at = "success", result, datetime.now(UTC)
                else:
                    message = "执行进程中断，恢复后将重新执行"
                    await s.abandon_running(session, row, message)
                    fail_run(row, message, datetime.now(UTC))
                    row.result = await s.result_of(session, row)
            await session.commit()

    async def claim_next(self, lane: str | None = None) -> tuple[uuid.UUID, str, uuid.UUID] | None:
        async with self.session_factory() as session:
            return await self.scheduler.claim_next_run(session, datetime.now(UTC), lane)

    def safe_error(self, exc: Exception, code: str) -> str:
        job = self.scheduler.jobs.get(code)
        if isinstance(exc, TimeoutError):
            minutes = int((job.timeout_seconds if job else DEFAULT_TIMEOUT) // 60)
            return f"执行超过 {minutes} 分钟，已中止本次执行，请检查数据源连接和执行范围"
        if isinstance(exc, UserFacingError):
            return str(exc)[:300]
        # 不把连接串、SQL 参数或凭据透传到页面。
        if isinstance(exc, RuntimeError) and job and job.public_errors and str(exc).startswith(job.public_errors):
            return str(exc)[:300]
        return f"执行失败（{type(exc).__name__}），请检查执行进程日志"

    async def execute(self, code: str, batch_id: uuid.UUID) -> dict[str, Any] | None:
        job = self.scheduler.jobs.get(code)
        if job is None:
            raise UserFacingError("未知任务，拒绝执行")
        return await job.execute(batch_id)

    async def execute_claim(self, claim: tuple[uuid.UUID, str, uuid.UUID]) -> None:
        run_id, code, batch_id = claim
        s = self.scheduler
        job = s.jobs.get(code)
        error = None
        retry = True
        output = None
        try:
            timeout = job.timeout_seconds if job else DEFAULT_TIMEOUT
            output = await asyncio.wait_for(self.execute(code, batch_id), timeout=timeout)
        except Exception as exc:  # noqa: BLE001  任何失败都要落到执行记录并按策略重试，不能让执行进程退出
            error = self.safe_error(exc, code)
            retry = not isinstance(exc, UserFacingError)
            self.logger.warning("scheduled_job_failed job=%s run=%s reason=%s", code, run_id, error)
        # CancelledError 留给进程退出后的 recover_interrupted。超时会进上面的 Exception。
        async with self.session_factory() as session:
            row = await session.get(s.run_model, run_id)
            if row is None:
                raise RuntimeError("执行记录丢失")
            await s.abandon_running(session, row, error or "同步批次未成功完成")
            row.result = await s.result_of(session, row)
            if output is not None and not (job and job.summary):
                row.result = output
            if job and job.summary:
                status = row.result.get("status") if row.result else None
                failure = claim_failure(error, status if isinstance(status, str) else None)
            else:
                failure = error
            if failure:
                fail_run(row, failure, datetime.now(UTC), retry=retry)
            else:
                row.status, row.finished_at, row.error_message = "success", datetime.now(UTC), None
            await session.commit()

    async def heartbeat(self, connection: AsyncConnection) -> None:
        model = self.scheduler.heartbeat_model
        while True:
            now = datetime.now(UTC)
            stmt = insert(model).values(id=1, seen_at=now)
            await connection.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={"seen_at": now}))
            await connection.commit()
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def drain(self, lane: str) -> None:
        """一条通道：领一条、执行完再领下一条，没有就隔一会儿再看。

        领取时库暂时不可用不往外抛：抛出去会让整个 leader 重启，把别的通道里跑了几个小时的任务也中断。
        这次领取有没有提交说不准，下次领取前先回收这条通道停在 running 的记录（此刻本通道没在执行任何任务）。
        执行完落记录失败照旧往外抛，由 leader 重启后统一回收。
        """

        unsure = False
        while True:
            try:
                if unsure:
                    await self.recover_interrupted(lane)
                    unsure = False
                claim = await self.claim_next(lane)
            except Exception as exc:  # noqa: BLE001  库暂时不可用时等一会儿再领，不能连累别的通道
                unsure = True
                self.logger.warning("scheduler_claim_failed lane=%s reason=%s", lane, type(exc).__name__)
                await asyncio.sleep(POLL_SECONDS)
                continue
            if claim:
                await self.execute_claim(claim)
            else:
                await asyncio.sleep(POLL_SECONDS)

    async def consume(self) -> None:
        await self.recover_interrupted()
        # 一条通道出错时 TaskGroup 取消其余通道，由 leader 统一收尾、重启后回收。
        # 没登记任务时也留一条空通道轮询，不让 leader 反复抢锁放锁。
        async with asyncio.TaskGroup() as group:
            for lane in self.scheduler.lanes or [SHORT_LANE]:
                group.create_task(self.drain(lane))

    async def lead(self, stop: asyncio.Event) -> None:
        async with self.engine.connect() as connection:
            locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.leader_lock})
            await connection.commit()
            if not locked:
                await asyncio.sleep(POLL_SECONDS)
                return
            tasks = [
                asyncio.create_task(self.heartbeat(connection)),
                asyncio.create_task(self.consume()),
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
                # 先停任务，再释放 leader 锁，避免新进程接管时旧任务仍继续写。
                with contextlib.suppress(Exception):
                    await connection.rollback()
                    await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.leader_lock})
                    await connection.commit()

    async def run(self, stop: asyncio.Event) -> None:
        """常驻到 stop 置位。数据库或锁暂时不可用时等待后重试，不退出。"""

        while not stop.is_set():
            try:
                await self.lead(stop)
            except Exception as exc:  # noqa: BLE001  数据库或锁暂时不可用时等待后重试，调度进程常驻不退出
                # 通道在 TaskGroup 里跑，出错时包成 ExceptionGroup，日志写里面真正的异常类型。
                causes = exc.exceptions if isinstance(exc, ExceptionGroup) else (exc,)
                self.logger.warning("scheduler_unavailable reason=%s", ",".join(type(item).__name__ for item in causes))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)

    async def main(self) -> None:
        """独立执行进程的入口：收到 SIGTERM/SIGINT 先停任务再退出。"""

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await self.run(stop)
        await self.engine.dispose()

    async def healthy(self) -> bool:
        """容器健康检查：最近一分钟内有心跳。"""

        async with self.session_factory() as session:
            row = await session.get(self.scheduler.heartbeat_model, 1)
        return row is not None and datetime.now(UTC) - row.seen_at < ONLINE_WITHIN
