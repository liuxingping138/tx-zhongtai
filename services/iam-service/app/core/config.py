"""iam-service 配置。所有环境变量使用 `IAM_` 前缀。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platform_common.config import BaseServiceSettings, Environment
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="IAM_", env_file=".env", extra="ignore")

    service_name: str = "iam-service"
    http_port: int = 8001

    database_url: str
    redis_url: str

    cors_allow_origins: list[str] = []
    csrf_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    jwt_issuer: str = "tx-zhongtai-iam"
    jwt_audience: str = "tx-zhongtai"
    jwt_algorithm: str = "RS256"
    jwt_keys_dir: str = ".jwt-keys"
    access_token_ttl_seconds: int = 8 * 3600
    refresh_token_ttl_seconds: int = 7 * 24 * 3600
    refresh_reuse_grace_seconds: int = 30

    refresh_cookie_name: str = "refresh_token"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False
    cookie_samesite: str = "strict"

    # 账号维度：同一账号连续失败次数上限。
    login_max_failures: int = 5
    # IP 维度：同一来源 IP 的失败次数上限。同一出口可能有多人，比账号维度宽；登录成功不清零。
    login_max_failures_per_ip: int = 20
    login_lockout_seconds: int = 300
    # 会话与刷新令牌失效后的额外保留天数，供回溯近期登录情况；到期由清理任务删除。
    session_retention_days: int = 30

    # 内部调用方：service_name -> 共享密钥。生产环境字段名含 secret，会被演示值检查拦截。
    internal_caller_secrets: dict[str, str] = Field(default_factory=dict)

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    worker_batch_size: int = 20
    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 30
    worker_max_attempts: int = 8
    worker_backoff_base_seconds: int = 2
    worker_backoff_cap_seconds: int = 300

    @model_validator(mode="after")
    def _reject_demo_internal_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret")
            tokens = list(self.internal_caller_secrets.values())
            if self.audit_ingest_secret:
                tokens.append(self.audit_ingest_secret)
            for token in tokens:
                if any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self

    @property
    def jwt_keys_path(self) -> Path:
        return Path(self.jwt_keys_dir)

    @property
    def allow_generate_jwt_keys(self) -> bool:
        return self.environment in {Environment.DEVELOPMENT, Environment.TEST}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
