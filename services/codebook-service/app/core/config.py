"""codebook-service 配置。环境变量前缀 `CODEBOOK_`。"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="CODEBOOK_", env_file=".env", extra="ignore")

    service_name: str = "codebook-service"
    http_port: int = 8003
    database_url: str
    cors_allow_origins: list[str] = []

    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    worker_poll_interval_seconds: float = 2.0
    worker_max_attempts: int = 8
    import_max_bytes: int = 20 * 1024 * 1024

    @model_validator(mode="after")
    def _reject_demo_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
            for token in (self.iam_service_secret, self.audit_ingest_secret):
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
