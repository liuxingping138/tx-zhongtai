"""调度的查询和页面操作：列任务、改计划、手动执行、执行记录、领取下一条。HTTP 进程和 worker 共用。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.actors import Actor
from platform_common.errors import NotFoundError, VersionConflictError
from platform_common.scheduler.jobs import ACTIVE, Job, next_daily

ONLINE_WITHIN = timedelta(seconds=60)
# 与 AuditEmitter.enqueue_event 同签名：(session, *, event_type, actor, target_id, changes|extra)
AuditHook = Callable[..., Awaitable[None]]


class Scheduler:
    """一个服务的调度：绑定本服务的三张表、登记的任务和审计入队。"""

    def __init__(
        self,
        *,
        jobs: Sequence[Job],
        job_model: type[Any],
        run_model: type[Any],
        heartbeat_model: type[Any],
        audit: AuditHook,
    ) -> None:
        # 页面按登记顺序列出任务。
        self.jobs = {job.code: job for job in jobs}
        # 执行通道按登记顺序；执行进程每条通道一个循环。
        self.lanes = list(dict.fromkeys(job.lane for job in jobs))
        self.job_model = job_model
        self.run_model = run_model
        self.heartbeat_model = heartbeat_model
        self._audit = audit

    def job(self, code: str) -> Job:
        if code not in self.jobs:
            raise NotFoundError("任务不存在")
        return self.jobs[code]

    def lane_codes(self, lane: str | None) -> list[str]:
        """这条通道的任务编码；None 是全部任务。"""

        return [code for code, job in self.jobs.items() if lane is None or job.lane == lane]

    def run_data(self, row: Any) -> dict[str, Any]:
        return {col.name: getattr(row, col.name) for col in self.run_model.__table__.columns}

    async def get_job(self, session: AsyncSession, code: str, *, lock: bool = False) -> Any:
        self.job(code)
        stmt = select(self.job_model).where(self.job_model.code == code)
        if lock:
            stmt = stmt.with_for_update()
        row = await session.scalar(stmt)
        if row is None:
            raise NotFoundError("任务尚未初始化，请执行数据库迁移")
        return row

    async def active_run(self, session: AsyncSession, code: str) -> Any | None:
        run = self.run_model
        return await session.scalar(select(run).where(run.job_code == code, run.status.in_(ACTIVE)))

    async def enqueue(self, session: AsyncSession, job: Any, now: datetime, *, trigger: str, actor_name: str) -> Any:
        # 调用方持有 job 行锁；唯一部分索引是第二道并发保护。
        if await self.active_run(session, job.code):
            raise VersionConflictError("该任务已在排队、执行或等待重试，请勿重复提交")
        row = self.run_model(
            job_code=job.code,
            trigger=trigger,
            actor_name=actor_name,
            status="queued",
            attempts=0,
            created_at=now,
            scheduled_at=job.next_run_at if trigger == "scheduled" else now,
            available_at=now,
        )
        session.add(row)
        await session.flush()
        return row

    async def schedule_due(self, session: AsyncSession, now: datetime) -> None:
        model = self.job_model
        due = (
            await session.scalars(
                select(model)
                .where(model.enabled.is_(True), model.next_run_at <= now, model.code.in_(list(self.jobs)))
                .order_by(model.code)
                .with_for_update()
            )
        ).all()
        for job in due:
            # 已有任务合并此次计划；积压多天只排一个，不逐天重复入队。
            if not await self.active_run(session, job.code):
                await self.enqueue(session, job, now, trigger="scheduled", actor_name="每日计划")
            job.next_run_at = next_daily(now, job.daily_time)

    async def abandon_running(self, session: AsyncSession, row: Any, message: str) -> None:
        """超时或进程中断时，让任务把仍停在 running 的批次收成失败。

        ``wait_for`` 取消任务只会抛出 CancelledError，任务自己的 ``except Exception`` 接不住，
        批次会永远停在 running。这里在调度事务里收口。
        """

        job = self.jobs.get(row.job_code)
        if row.sync_run_id is not None and job and job.abandon:
            await job.abandon(session, row.sync_run_id, message)

    async def result_of(self, session: AsyncSession, row: Any) -> dict[str, Any] | None:
        job = self.jobs.get(row.job_code)
        if row.sync_run_id is None or job is None or job.summary is None:
            return row.result  # type: ignore[no-any-return]  # ORM 行是 Any，JSONB 列就是 dict | None
        return await job.summary(session, row.sync_run_id) or row.result

    async def list_jobs(self, session: AsyncSession) -> dict[str, Any]:
        heartbeat = await session.get(self.heartbeat_model, 1)
        now = datetime.now(UTC)
        order = list(self.jobs)
        rows = sorted(
            (row for row in (await session.scalars(select(self.job_model))).all() if row.code in self.jobs),
            key=lambda row: order.index(row.code),
        )
        items = []
        for row in rows:
            job = self.jobs[row.code]
            last = await self._last_run(session, row.code)
            active = await self.active_run(session, row.code)
            items.append(
                {
                    "code": row.code,
                    "name": job.name,
                    "cost_resource": job.cost_resource,
                    "enabled": row.enabled,
                    "daily_time": row.daily_time,
                    "next_run_at": row.next_run_at if row.enabled else None,
                    "version": row.version,
                    "watermark": await job.watermark(session) if job.watermark else None,
                    "active_run": self.run_data(active) if active else None,
                    "last_run": self.run_data(last) if last else None,
                }
            )
        return {
            "items": items,
            "timezone": "Asia/Shanghai",
            "worker_online": bool(heartbeat and now - heartbeat.seen_at < ONLINE_WITHIN),
            "heartbeat_at": heartbeat.seen_at if heartbeat else None,
        }

    async def _last_run(self, session: AsyncSession, code: str) -> Any | None:
        run = self.run_model
        return await session.scalar(select(run).where(run.job_code == code).order_by(run.created_at.desc()).limit(1))

    async def update_job(
        self, session: AsyncSession, code: str, actor: Actor, *, enabled: bool, daily_time: str, version: int
    ) -> None:
        job = await self.get_job(session, code, lock=True)
        if version != job.version:
            raise VersionConflictError("计划已被其他人修改，请刷新后重新设置")
        before = {"enabled": job.enabled, "daily_time": job.daily_time}
        # 停用取消尚未开始和等待重试的请求；已在执行的批次跑完当前这次。
        active = await self.active_run(session, code)
        if not enabled and active and active.status in {"queued", "retrying"}:
            active.status = "cancelled"
            active.finished_at = datetime.now(UTC)
            active.error_message = "每日计划停用，待执行请求已取消"
        if daily_time != job.daily_time or enabled != job.enabled:
            job.next_run_at = next_daily(datetime.now(UTC), daily_time)
        job.enabled = enabled
        job.daily_time = daily_time
        job.version += 1
        await self._audit(
            session,
            event_type="scheduler.updated",
            actor=actor,
            target_id=code,
            changes={"before": before, "after": {"enabled": enabled, "daily_time": daily_time}},
        )

    async def trigger_job(self, session: AsyncSession, code: str, actor: Actor) -> dict[str, Any]:
        job = await self.get_job(session, code, lock=True)
        row = await self.enqueue(session, job, datetime.now(UTC), trigger="manual", actor_name=actor.name)
        await self._audit(
            session, event_type="scheduler.triggered", actor=actor, target_id=code, extra={"run_id": str(row.id)}
        )
        return self.run_data(row)

    async def run_status(self, session: AsyncSession, code: str) -> dict[str, Any]:
        """业务页面上「立即同步」旁的状态：正在排队或执行的那次，以及最近一次执行和它的结果。"""

        active = await self.active_run(session, code)
        last = await self._last_run(session, code)
        last_data = {**self.run_data(last), "result": await self.result_of(session, last)} if last else None
        return {"active_run": self.run_data(active) if active else None, "last_run": last_data}

    async def history(self, session: AsyncSession, code: str, page: int, page_size: int) -> dict[str, Any]:
        await self.get_job(session, code)
        run = self.run_model
        where = run.job_code == code
        total = await session.scalar(select(func.count()).select_from(run).where(where)) or 0
        rows = (
            await session.scalars(
                select(run)
                .where(where)
                .order_by(run.created_at.desc(), run.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [{**self.run_data(row), "result": await self.result_of(session, row)} for row in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def claim_next_run(
        self, session: AsyncSession, now: datetime, lane: str | None = None
    ) -> tuple[uuid.UUID, str, uuid.UUID] | None:
        """把到点的计划入队，再从这条通道（None 是不分通道）领取一条可执行的任务置为 running；没有可执行的返回 None。

        入队不分通道：长通道在跑的几个小时里，到点的长任务照样显示「排队中」，空出来就接着跑。
        几条通道同时入队靠任务行锁排队，后到的看到计划时间已前移就跳过，不会重复入队。
        """

        await self.schedule_due(session, now)
        await session.commit()
        run = self.run_model
        candidate = await session.scalar(
            select(run.job_code)
            .where(
                run.status.in_(("queued", "retrying")),
                run.available_at <= now,
                run.job_code.in_(self.lane_codes(lane)),
            )
            .order_by(run.available_at, run.created_at)
            .limit(1)
        )
        if candidate is None:
            return None
        # 与页面停用/入队使用相同的锁顺序：job -> run。
        await self.get_job(session, candidate, lock=True)
        row = await self.active_run(session, candidate)
        if row is None or row.status not in {"queued", "retrying"} or row.available_at > now:
            return None
        row.status = "running"
        row.started_at = row.started_at or now
        row.attempts += 1
        row.sync_run_id = uuid.uuid4()
        await session.commit()
        return row.id, row.job_code, row.sync_run_id
