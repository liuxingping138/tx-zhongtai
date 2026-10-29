"""调度路由工厂：四个接口各挂对应档位的权限、都声明了分级；leader 选举拿不到锁就让出，拿到锁退出时释放。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from platform_common.actors import Actor
from platform_common.errors import register_exception_handlers
from platform_common.route_audit import audit_routes, mark_permission_dependency
from platform_common.scheduler import Job, Scheduler, SchedulerRunner, build_scheduler_router
from platform_common.scheduler import runner as runner_module

from .scheduler_tables import tables

ACTOR = Actor(id="u1", name="管理员")


async def _noop(_batch: uuid.UUID) -> None:
    return None


def _app(scheduler: Scheduler, granted: set[str], cost_granted: set[str] | None = None) -> FastAPI:
    def require_permission(resource: str, action: str) -> Any:
        async def dependency() -> Actor:
            from platform_common.errors import PermissionDeniedError

            assert resource == "system.scheduler"
            if action not in granted:
                raise PermissionDeniedError()
            return ACTOR

        return mark_permission_dependency(dependency, resource=resource, action=action)

    async def get_db_session() -> AsyncIterator[object]:
        yield object()

    async def check_permission(_request: object, resource: str, action: str) -> None:
        from platform_common.errors import PermissionDeniedError

        assert resource == "demo.spend"
        if action not in (cost_granted or set()):
            raise PermissionDeniedError()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_scheduler_router(
            scheduler,
            prefix="/api/v1/demo/scheduled-jobs",
            require_permission=require_permission,
            get_db_session=get_db_session,
            check_permission=check_permission,
        )
    )
    return app


@pytest.fixture
def scheduler(monkeypatch: pytest.MonkeyPatch) -> Scheduler:
    jobs = [Job("cleanup", "清理", _noop), Job("ai", "调模型", _noop, cost_resource="demo.spend")]
    s = Scheduler(jobs=jobs, **tables(), audit=AsyncMock())
    monkeypatch.setattr(s, "list_jobs", AsyncMock(return_value={"items": [], "worker_online": True}))
    monkeypatch.setattr(s, "update_job", AsyncMock())
    monkeypatch.setattr(s, "trigger_job", AsyncMock(return_value={"status": "queued"}))
    monkeypatch.setattr(s, "history", AsyncMock(return_value={"items": [], "total": 0}))
    return s


def test_every_route_is_classified_and_guarded(scheduler: Scheduler) -> None:
    assert audit_routes(_app(scheduler, set())) == []


async def test_read_tier_can_list_but_not_change(scheduler: Scheduler) -> None:
    base = "/api/v1/demo/scheduled-jobs"
    plan = {"enabled": True, "daily_time": "03:00", "version": 1}
    transport = httpx.ASGITransport(app=_app(scheduler, {"list"}))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(base)).json()["data"]["worker_online"] is True
        assert (await client.get(f"{base}/cleanup/runs", params={"page": 2})).status_code == 200
        assert (await client.post(f"{base}/cleanup/runs")).status_code == 403
        assert (await client.patch(f"{base}/cleanup", json=plan)).status_code == 403


async def test_full_tier_changes_the_plan_and_queues_a_run(scheduler: Scheduler) -> None:
    base = "/api/v1/demo/scheduled-jobs"
    transport = httpx.ASGITransport(app=_app(scheduler, {"list", "update", "execute"}))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.patch(f"{base}/cleanup", json={"enabled": True, "daily_time": "25:00", "version": 1})
        assert bad.status_code == 422
        ok = await client.patch(f"{base}/cleanup", json={"enabled": False, "daily_time": "03:00", "version": 1})
        assert ok.json()["data"] == {"saved": True}
        queued = await client.post(f"{base}/cleanup/runs")
        assert queued.status_code == 202 and queued.json()["data"]["status"] == "queued"
    update = scheduler.update_job
    assert isinstance(update, AsyncMock) and update.await_args is not None
    assert update.await_args.kwargs == {"enabled": False, "daily_time": "03:00", "version": 1}


async def test_jobs_that_spend_money_also_need_their_own_permission(scheduler: Scheduler) -> None:
    """能排班的人不一定能决定花钱：带 cost_resource 的任务改计划、立即执行还要那个资源；不花钱的任务不受影响。"""

    base = "/api/v1/demo/scheduled-jobs"
    plan = {"enabled": True, "daily_time": "03:00", "version": 1}
    scheduler_only = httpx.ASGITransport(app=_app(scheduler, {"list", "update", "execute"}))
    async with httpx.AsyncClient(transport=scheduler_only, base_url="http://test") as client:
        assert (await client.post(f"{base}/ai/runs")).status_code == 403
        assert (await client.patch(f"{base}/ai", json=plan)).status_code == 403
        assert (await client.post(f"{base}/cleanup/runs")).status_code == 202
    both = httpx.ASGITransport(app=_app(scheduler, {"list", "update", "execute"}, {"update", "execute"}))
    async with httpx.AsyncClient(transport=both, base_url="http://test") as client:
        assert (await client.post(f"{base}/ai/runs")).status_code == 202
        assert (await client.patch(f"{base}/ai", json=plan)).status_code == 200


class _Connection:
    def __init__(self, locked: bool) -> None:
        self.locked = locked
        self.statements: list[str] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def scalar(self, stmt: Any, *_: Any) -> bool:
        self.statements.append(str(stmt))
        return self.locked

    async def execute(self, stmt: Any, *_: Any) -> None:
        self.statements.append(str(stmt))

    async def __aenter__(self) -> _Connection:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _runner(connection: _Connection) -> SchedulerRunner:
    engine = type("Engine", (), {"connect": lambda self: connection})()
    s = Scheduler(jobs=[Job("cleanup", "清理", _noop)], **tables(), audit=AsyncMock())
    return SchedulerRunner(s, engine=engine, session_factory=AsyncMock(), leader_lock=7, logger_name="t")  # type: ignore[arg-type]


async def test_without_the_lock_it_steps_aside(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "POLL_SECONDS", 0)
    connection = _Connection(locked=False)
    runner = _runner(connection)
    runner.consume = AsyncMock()  # type: ignore[method-assign]
    await runner.lead(asyncio.Event())
    runner.consume.assert_not_awaited()
    assert not any("unlock" in stmt for stmt in connection.statements)


async def test_the_leader_works_until_stopped_then_releases_the_lock() -> None:
    connection = _Connection(locked=True)
    runner = _runner(connection)
    stop = asyncio.Event()

    async def consume() -> None:
        stop.set()
        await asyncio.sleep(60)

    runner.consume = consume  # type: ignore[method-assign]
    await asyncio.wait_for(runner.lead(stop), timeout=1)
    assert any("pg_advisory_unlock" in stmt for stmt in connection.statements)
    assert any("scheduler_heartbeat" in stmt for stmt in connection.statements)
