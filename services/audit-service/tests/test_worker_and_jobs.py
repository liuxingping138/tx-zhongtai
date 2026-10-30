"""audit-worker：每天用清理账号删到期的操作日志，删完用应用账号记一条清理审计。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application import scheduled_jobs


class _Ctx:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *_: object) -> None:
        return None


async def test_cleanup_deletes_with_the_cleanup_account_and_releases_its_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        cleanup_database_url="postgresql+asyncpg://audit_cleanup:x@db/audit",
        database_url="postgresql+asyncpg://audit_app:x@db/audit",
        retention_days=180,
        max_event_bytes=32_768,
    )
    engine = SimpleNamespace(dispose=AsyncMock())
    urls: list[str] = []
    cleanup_session, app_session = object(), object()

    def create_engine(url: str, **_: Any) -> Any:
        urls.append(url)
        return engine

    recorded = AsyncMock()
    monkeypatch.setattr(scheduled_jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduled_jobs, "create_async_engine", create_engine)
    monkeypatch.setattr(scheduled_jobs, "async_sessionmaker", lambda *_a, **_k: lambda: _Ctx(cleanup_session))
    monkeypatch.setattr(scheduled_jobs, "delete_expired", AsyncMock(return_value=42))
    monkeypatch.setattr(scheduled_jobs, "SessionLocal", lambda: _Ctx(app_session))
    monkeypatch.setattr(scheduled_jobs, "record_cleanup", recorded)

    assert await scheduled_jobs.run_cleanup(uuid.uuid4()) == {"deleted": 42, "retention_days": 180}
    assert urls == [settings.cleanup_database_url]
    engine.dispose.assert_awaited_once()
    assert recorded.await_args is not None and recorded.await_args.args == (app_session,)
    assert recorded.await_args.kwargs["deleted"] == 42


async def test_worker_runs_the_scheduler_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.worker import __main__ as worker

    seen: list[Any] = []

    async def run(stop: Any) -> None:
        seen.append(stop)

    monkeypatch.setattr(worker.runner, "run", run)
    await worker.run()
    assert len(seen) == 1
    assert worker.runner.leader_lock == worker.SCHEDULER_LOCK
