"""公共基础件：时间格式、健康检查、生产配置拒绝示例密钥、日志脱敏。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import Field, ValidationError

from platform_common.clock import BEIJING, format_beijing, utcnow
from platform_common.config import BaseServiceSettings, Environment
from platform_common.health import build_health_router
from platform_common.logging_setup import get_logger, setup_logging


class TestClock:
    def test_utcnow_carries_a_timezone(self) -> None:
        assert utcnow().tzinfo is UTC

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, ""),
            ("", ""),
            (datetime(2026, 10, 10, 0, 0, tzinfo=UTC), "2026-10-10 08:00:00"),
            (datetime(2026, 10, 10, 0, 0), "2026-10-10 08:00:00"),
            (datetime(2026, 10, 10, 8, 0, tzinfo=timezone(timedelta(hours=8))), "2026-10-10 08:00:00"),
            ("2026-10-10T00:00:00Z", "2026-10-10 08:00:00"),
            ("2026-10-10T00:00:00", "2026-10-10 08:00:00"),
            ("2026-10-10", "2026-10-10"),
            ("not-a-dateTZ", "not-a-dateTZ"),
        ],
    )
    def test_format_beijing(self, value: object, expected: str) -> None:
        assert format_beijing(value) == expected

    def test_beijing_is_utc_plus_eight(self) -> None:
        assert BEIJING.utcoffset(None) == timedelta(hours=8)


class TestHealth:
    def _client(self, checks: dict | None) -> TestClient:  # type: ignore[type-arg]
        app = FastAPI()
        app.include_router(build_health_router(checks))
        return TestClient(app)

    def test_live_never_looks_at_dependencies(self) -> None:
        async def boom() -> bool:
            raise RuntimeError

        assert self._client({"db": boom}).get("/health/live").json() == {"status": "live"}

    def test_ready_without_checks_is_ready(self) -> None:
        assert self._client(None).get("/health/ready").json() == {"status": "ready", "checks": {}}

    def test_a_failing_or_raising_dependency_makes_it_unavailable(self) -> None:
        async def ok() -> bool:
            return True

        async def down() -> bool:
            return False

        async def boom() -> bool:
            raise ConnectionError("secret-host")

        response = self._client({"db": ok, "redis": down, "queue": boom}).get("/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready" and body["checks"] == {"db": True, "redis": False, "queue": False}
        assert "secret-host" not in response.text

    def test_all_dependencies_up(self) -> None:
        async def ok() -> bool:
            return True

        response = self._client({"db": ok}).get("/health/ready")
        assert response.status_code == 200 and response.json()["status"] == "ready"


class _Settings(BaseServiceSettings):
    jwt_secret: str = "real-value"
    database_url: str = "postgresql+asyncpg://app:R3alPass@db:5432/app_db"
    internal_caller_secrets: dict[str, str] = Field(default_factory=lambda: {"policy-service": "x9Zk2Lq8Vw"})
    ark_api_key: str = ""


class TestConfig:
    def test_demo_secrets_are_fine_outside_production(self) -> None:
        assert _Settings(environment=Environment.DEVELOPMENT, jwt_secret="dev-secret").jwt_secret == "dev-secret"

    @pytest.mark.parametrize("secret", ["dev-secret", "Example-Key", "changeme", "test-secret-1"])
    def test_production_refuses_demo_secrets(self, secret: str) -> None:
        with pytest.raises(ValidationError, match="示例/演示密钥"):
            _Settings(environment=Environment.PRODUCTION, jwt_secret=secret)

    def test_production_checks_the_password_inside_the_database_url(self) -> None:
        """口令拼在连接串里，按字段名查不到它：服务器沿用示例口令照样能启动，而 5433 对公网开放。"""

        with pytest.raises(ValidationError, match="database_url 里的口令"):
            _Settings(environment=Environment.PRODUCTION, database_url="postgresql://app:dev-only-pw@db/app")

    def test_production_checks_every_value_of_a_secret_dict(self) -> None:
        with pytest.raises(ValidationError, match=r"internal_caller_secrets\[ai-service\]"):
            _Settings(environment=Environment.PRODUCTION, internal_caller_secrets={"ai-service": "dev-only-ai"})
        with pytest.raises(ValidationError, match="是空的"):
            _Settings(environment=Environment.PRODUCTION, internal_caller_secrets={})

    def test_production_refuses_empty_secrets_but_allows_an_unused_vendor_key(self) -> None:
        with pytest.raises(ValidationError, match="jwt_secret 是空的"):
            _Settings(environment=Environment.PRODUCTION, jwt_secret="")
        # 没配的那家模型在页面上显示不可用，不是配置错误。
        assert _Settings(environment=Environment.PRODUCTION, ark_api_key="").ark_api_key == ""

    def test_production_accepts_a_real_looking_secret(self) -> None:
        assert (
            _Settings(environment=Environment.PRODUCTION, jwt_secret="x9Zk2Lq8Vw").environment == Environment.PRODUCTION
        )


class TestLogging:
    def test_sensitive_keys_are_redacted_in_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging("unit", level="INFO", json_output=True)
        get_logger("unit").info("login", username="zhangsan", password="hunter2")
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
        login = next(line for line in lines if line["event"] == "login")
        assert login["username"] == "zhangsan"
        assert "hunter2" not in json.dumps(login)
