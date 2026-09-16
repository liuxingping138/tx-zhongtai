"""audit-service 配置。所有环境变量使用 `AUDIT_` 前缀。"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env", extra="ignore")

    service_name: str = "audit-service"
    http_port: int = 8002

    database_url: str

    cors_allow_origins: list[str] = []

    # 允许调用内部写入接口的来源服务凭据在 P2/P5 阶段接入时补充。
    retention_days: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
