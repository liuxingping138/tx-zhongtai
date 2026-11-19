"""统一的异步数据库引擎工厂：支持连接池配置与 PostgreSQL 语句/空闲事务超时保护。"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def create_service_engine(  # noqa: PLR0913  引擎工厂统一收口连接池与超时参数，调用方按关键字传参
    url: str,
    *,
    service_name: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: float = 30.0,
    statement_timeout_ms: int = 60_000,
    idle_in_transaction_timeout_ms: int = 120_000,
    use_env_overrides: bool = True,
) -> AsyncEngine:
    size = _env_int("DB_POOL_SIZE", pool_size) if use_env_overrides else pool_size
    overflow = _env_int("DB_MAX_OVERFLOW", max_overflow) if use_env_overrides else max_overflow
    stmt_ms = _env_int("DB_STATEMENT_TIMEOUT_MS", statement_timeout_ms) if use_env_overrides else statement_timeout_ms
    idle_ms = (
        _env_int("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", idle_in_transaction_timeout_ms)
        if use_env_overrides
        else idle_in_transaction_timeout_ms
    )
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "echo": False,
        "pool_size": size,
        "max_overflow": overflow,
        "pool_timeout": pool_timeout,
    }
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {
            "server_settings": {
                "application_name": service_name,
                "statement_timeout": str(stmt_ms),
                "idle_in_transaction_session_timeout": str(idle_ms),
            }
        }
    return create_async_engine(url, **kwargs)
