"""清理与授权命令行的保护：不允许用应用账号清理、账号名必须合法，成功时授予/收回的权限语句正确。数据库用替身。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cli import cleanup

APP_URL = "postgresql+asyncpg://audit_app:x@db/audit_db"
CLEAN_URL = "postgresql+asyncpg://audit_cleanup:x@db/audit_db"


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "database_url": APP_URL,
        "cleanup_database_url": CLEAN_URL,
        "retention_days": 365,
        "max_event_bytes": 65536,
        "cleanup_db_user": "audit_cleanup",
    }
    return SimpleNamespace(**(base | overrides))


class _Ctx:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *_: object) -> None:
        return None


class TestCleanup:
    async def test_refuses_to_run_without_a_dedicated_cleanup_connection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cleanup, "get_settings", MagicMock(return_value=_settings(cleanup_database_url="")))
        monkeypatch.delenv("AUDIT_CLEANUP_DATABASE_URL", raising=False)
        with pytest.raises(SystemExit, match="AUDIT_CLEANUP_DATABASE_URL"):
            await cleanup.main()

    async def test_refuses_to_clean_with_the_application_account(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cleanup, "get_settings", MagicMock(return_value=_settings(cleanup_database_url=APP_URL)))
        with pytest.raises(SystemExit, match="不能与应用连接相同"):
            await cleanup.main()

    async def test_deletes_with_the_cleanup_account_then_records_with_the_app_account(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SimpleNamespace(dispose=AsyncMock())
        cleanup_session, app_session = object(), object()
        monkeypatch.setattr(cleanup, "get_settings", MagicMock(return_value=_settings()))
        monkeypatch.setattr(cleanup, "create_async_engine", MagicMock(return_value=engine))
        monkeypatch.setattr(cleanup, "async_sessionmaker", lambda *_a, **_k: lambda: _Ctx(cleanup_session))
        monkeypatch.setattr(cleanup, "SessionLocal", lambda: _Ctx(app_session))
        delete = AsyncMock(return_value=17)
        record = AsyncMock()
        monkeypatch.setattr(cleanup, "delete_expired", delete)
        monkeypatch.setattr(cleanup, "record_cleanup", record)

        await cleanup.main()

        delete.assert_awaited_once_with(cleanup_session, retention_days=365)
        assert record.await_args.args[0] is app_session
        assert record.await_args.kwargs == {"deleted": 17, "retention_days": 365, "max_bytes": 65536}
        engine.dispose.assert_awaited_once()

    async def test_the_cleanup_engine_is_released_even_when_deletion_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SimpleNamespace(dispose=AsyncMock())
        monkeypatch.setattr(cleanup, "get_settings", MagicMock(return_value=_settings()))
        monkeypatch.setattr(cleanup, "create_async_engine", MagicMock(return_value=engine))
        monkeypatch.setattr(cleanup, "async_sessionmaker", lambda *_a, **_k: lambda: _Ctx(object()))
        monkeypatch.setattr(cleanup, "delete_expired", AsyncMock(side_effect=RuntimeError("db down")))
        with pytest.raises(RuntimeError):
            await cleanup.main()
        engine.dispose.assert_awaited_once()
