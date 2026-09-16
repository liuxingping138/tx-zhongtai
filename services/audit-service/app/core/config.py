"""audit-service 配置。所有环境变量使用 `AUDIT_` 前缀。"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env", extra="ignore")

    service_name: str = "audit-service"
    http_port: int = 8002

    database_url: str
    cleanup_database_url: str | None = None
    cleanup_db_user: str = "audit_cleanup"

    cors_allow_origins: list[str] = []
    retention_days: int = 180
    max_event_bytes: int = 32_768

    internal_caller_secrets: dict[str, str] = Field(default_factory=dict)
    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0

    @model_validator(mode="after")
    def _reject_demo_internal_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret")
            for token in list(self.internal_caller_secrets.values()) + [self.iam_service_secret]:
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
