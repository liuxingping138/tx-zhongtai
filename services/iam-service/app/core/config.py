"""iam-service 配置。

所有环境变量使用 `IAM_` 前缀，避免与其他服务的同名变量混淆
（例如两个服务各自的 `DATABASE_URL` 必须分别是 `IAM_DATABASE_URL`
和 `AUDIT_DATABASE_URL`，指向各自独立的数据库和账号）。
"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="IAM_", env_file=".env", extra="ignore")

    service_name: str = "iam-service"
    http_port: int = 8001

    database_url: str
    redis_url: str

    cors_allow_origins: list[str] = []

    # JWT 相关配置在 P2 阶段接入具体实现时补充校验（密钥文件路径、算法、kid 等）。
    jwt_issuer: str = "tx-zhongtai-iam"
    jwt_audience: str = "tx-zhongtai"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 7 * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
