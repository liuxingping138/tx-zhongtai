"""iam-service 配置。所有环境变量使用 `IAM_` 前缀。"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path

from platform_common.config import BaseServiceSettings, Environment
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from app.domain.networks import split_items


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
    # 在线用户：这么多秒内有过操作（带令牌的请求，含业务服务经 authorize 的请求）才算在线。
    online_window_seconds: int = 30 * 60
    # 「最近活跃」每台设备最多隔这么久写一次库，不是每个请求都写。
    session_touch_seconds: int = 60

    # 内部调用方：service_name -> 共享密钥。生产环境字段名含 secret，会被演示值检查拦截。
    internal_caller_secrets: dict[str, str] = Field(default_factory=dict)

    # 用户 Excel：账号数量远小于业务表，上限按「一次导入一个部门」设定。
    import_max_bytes: int = 5 * 1024 * 1024
    user_import_max_rows: int = 500
    export_max_rows: int = 100_000

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    worker_batch_size: int = 20
    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 30
    # 配合最长 15 分钟的退避，审计服务连不上能容忍约一天才置 dead（原来 8 次、三四分钟就放弃）。
    worker_max_attempts: int = 100
    worker_backoff_base_seconds: int = 2
    worker_backoff_cap_seconds: int = 900

    # 限定公司网络的模块：资源编码以这些前缀开头的（逗号分隔，目前只有智库），鉴权时还要核对来源 IP——
    # 在公司出口 office_networks 里直接放行，否则要这个人有没到期的访问白名单（系统管理 → 访问白名单）。
    # network_guard_enabled=false 关掉核对，只给 P6 这类从容器网络里访问、来源不是真实公网 IP 的环境用。
    network_guard_enabled: bool = True
    network_restricted_prefixes: str = "thinktank."
    office_networks: str = "1.119.196.74"
    # 白名单一次最长开多少天：到期要管理员续，免得临时开的口子变成永久的。
    whitelist_max_days: int = 365

    @model_validator(mode="after")
    def _check_network_settings(self) -> Settings:
        for item in split_items(self.office_networks):
            try:
                ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError(f"IAM_OFFICE_NETWORKS 里的「{item}」不是有效的 IP 或网段") from exc
        if self.network_guard_enabled and not split_items(self.office_networks):
            raise ValueError("开启了网络限制但 IAM_OFFICE_NETWORKS 为空，限定网络的模块所有人都进不去")
        if self.whitelist_max_days < 1:
            raise ValueError("IAM_WHITELIST_MAX_DAYS 至少为 1")
        return self

    @model_validator(mode="after")
    def _reject_demo_internal_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            if not self.cookie_secure:
                raise ValueError("生产环境必须启用 IAM_COOKIE_SECURE=true，避免刷新 Cookie 走明文传输")
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
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
    return Settings()  # type: ignore[call-arg]  # 必填项从环境变量读取，mypy 只看到构造参数缺失
