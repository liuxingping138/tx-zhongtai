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


@pytest.mark.parametrize(("raw", "expected"), [("0", "0"), ("", "60000"), ("-5", "60000"), ("abc", "60000")])
def test_zero_turns_the_timeouts_off_for_workers(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    # worker 跑几小时的同步、打标：0 是「不限」，不能被当成没设退回默认 60 秒 / 120 秒。
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", raw)
    monkeypatch.setenv("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", raw)
    captured: dict[str, object] = {}
    monkeypatch.setattr(database, "create_async_engine", lambda url, **kwargs: captured.update(kwargs))

    database.create_service_engine("postgresql+asyncpg://u:p@db:5432/app", service_name="policy-worker")

    settings = captured["connect_args"]["server_settings"]  # type: ignore[index]
    assert settings["statement_timeout"] == expected
    assert settings["idle_in_transaction_session_timeout"] == ("0" if raw == "0" else "120000")


def test_zero_pool_size_is_not_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    # SQLAlchemy 的 pool_size=0 是不限连接数，写 0 只能退回默认值。
    monkeypatch.setenv("DB_POOL_SIZE", "0")
    captured: dict[str, object] = {}
    monkeypatch.setattr(database, "create_async_engine", lambda url, **kwargs: captured.update(kwargs))

    database.create_service_engine("postgresql+asyncpg://u:p@db:5432/app", service_name="iam-service")

    assert captured["pool_size"] == 5
