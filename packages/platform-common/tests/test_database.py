"""统一数据库引擎工厂测试。"""

from __future__ import annotations

import pytest

from platform_common import database


def test_create_service_engine_sets_pg_server_settings_and_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "3")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "4")
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "45000")
    monkeypatch.setenv("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", "90000")

    captured: dict[str, object] = {}

    def fake_create(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_async_engine", fake_create)
    database.create_service_engine("postgresql+asyncpg://u:p@db:5432/app", service_name="iam-service")

    kw = captured["kwargs"]
    assert isinstance(kw, dict)
    assert kw["pool_size"] == 3 and kw["max_overflow"] == 4
    assert kw["connect_args"] == {
        "server_settings": {
            "application_name": "iam-service",
            "statement_timeout": "45000",
            "idle_in_transaction_session_timeout": "90000",
        }
    }

    captured.clear()
    database.create_service_engine("sqlite+aiosqlite:///:memory:", service_name="test", use_env_overrides=False)
    assert "connect_args" not in captured["kwargs"]  # type: ignore[operator]
