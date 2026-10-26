"""IAM 的定时任务：清理失效会话登记进公共调度、结果记进执行记录；页面接口按 system.scheduler 判权；审计写进 Outbox。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.actors import Actor
from platform_common.route_audit import permission_map

from app.application import scheduled_jobs
from app.application.event_map import _EVENT_META
from app.main import app


class _Db:
    def __call__(self) -> _Db:
        return self

    async def __aenter__(self) -> _Db:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def test_session_cleanup_is_the_registered_job() -> None:
    job = scheduled_jobs.scheduler.jobs["iam_session_cleanup"]
    assert job.name == "清理失效会话" and job.timeout_seconds == 600


async def test_cleanup_reports_what_it_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(tokens_deleted=5, sessions_deleted=2, tokens_remaining=40, sessions_remaining=9)
    cleanup = AsyncMock(return_value=result)
    monkeypatch.setattr(scheduled_jobs, "SessionLocal", _Db())
    monkeypatch.setattr(scheduled_jobs, "cleanup_sessions", cleanup)
    summary = await scheduled_jobs.run_session_cleanup(uuid.uuid4())
    retention = scheduled_jobs.get_settings().session_retention_days
    assert summary == {
        "retention_days": retention,
        "tokens_deleted": 5,
        "sessions_deleted": 2,
        "tokens_remaining": 40,
        "sessions_remaining": 9,
    }
    assert cleanup.await_args is not None and cleanup.await_args.kwargs == {"retention_days": retention}


async def test_audit_goes_into_the_outbox_with_the_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueue = AsyncMock()
    monkeypatch.setattr(scheduled_jobs.outbox_repo, "enqueue", enqueue)
    session: Any = object()
    actor = Actor(id="u1", name="管理员")
    await scheduled_jobs.enqueue_audit(
        session, event_type="scheduler.triggered", actor=actor, target_id="iam_session_cleanup", extra={"run_id": "r1"}
    )
    assert enqueue.await_args is not None
    payload = enqueue.await_args.kwargs["payload"]
    assert payload["actor_name"] == "管理员" and payload["target_id"] == "iam_session_cleanup"
    assert payload["run_id"] == "r1" and payload["outcome"] == "success"
    assert _EVENT_META["scheduler.triggered"][0] == "system.scheduler"


def test_scheduler_routes_are_guarded_by_system_scheduler() -> None:
    mapping = permission_map(app, covered_prefixes=("/api/",))
    base = "/api/v1/system/scheduled-jobs"
    assert mapping[f"GET {base}"] == ("system.scheduler", "list")
    assert mapping[f"PATCH {base}/{{code}}"] == ("system.scheduler", "update")
    assert mapping[f"POST {base}/{{code}}/runs"] == ("system.scheduler", "execute")
    assert mapping[f"GET {base}/{{code}}/runs"] == ("system.scheduler", "list")


async def test_the_page_records_the_operator_by_display_name() -> None:
    from app.api.scheduled_jobs import require_actor

    user_id = uuid.uuid4()
    principal: Any = SimpleNamespace(user=SimpleNamespace(id=user_id, display_name="张三"))
    actor = await require_actor("system.scheduler", "execute")(principal=principal)
    assert actor == Actor(id=str(user_id), name="张三")
