"""ai-service 配置。环境变量前缀 `AI_`。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platform_common.config import BaseServiceSettings, Environment
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    service_name: str = "ai-service"
    http_port: int = 8005
    database_url: str
    cors_allow_origins: list[str] = []

    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    # 模板引用系统码表时从码表服务的内部接口实时取。
    codebook_base_url: str = "http://codebook-service:8003"
    codebook_service_secret: str = ""
    codebook_timeout_seconds: float = 10.0
    # 允许调用 /internal/ 接口的服务及其密钥，如 {"policy-service": "..."}。
    internal_caller_secrets: dict[str, str] = Field(default_factory=dict)
    worker_poll_interval_seconds: float = 2.0
    worker_max_attempts: int = 8

    # 模板 Excel、码表和批量结果都落在这个目录（容器里挂持久卷），不放静态目录：静态目录谁都能下载。
    data_dir: Path = Path("/data/ai")
    upload_max_bytes: int = 20 * 1024 * 1024

    # 大模型密钥。没配的那家模型在下拉里显示为不可用，调用直接报错，不会悄悄换别家。
    ark_api_key: str = ""
    baidu_api_key: str = ""
    # 单条流式回答的读超时：联网搜索单条要几十秒，深度思考更久。
    llm_read_timeout_seconds: float = 600.0

    # 批量：同一个任务内的并发请求数，以及 worker 同时跑几个任务。并发过高会触发厂商限流。
    batch_concurrency: int = 20
    batch_max_running: int = 3
    # 运行中的任务超过这么久没有心跳，判定执行进程已经不在（重启、崩溃），标记为中断。
    batch_stale_seconds: int = 90

    @model_validator(mode="after")
    def _reject_demo_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
            secrets = (self.iam_service_secret, self.audit_ingest_secret, self.codebook_service_secret)
            for token in (*secrets, *self.internal_caller_secrets.values()):
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 必填项从环境变量读取，mypy 只看到构造参数缺失
