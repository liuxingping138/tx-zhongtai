"""thinktank-service 配置。环境变量前缀 `THINKTANK_`。"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="THINKTANK_", env_file=".env", extra="ignore")

    service_name: str = "thinktank-service"
    http_port: int = 8007
    database_url: str
    cors_allow_origins: list[str] = []

    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    codebook_base_url: str = ""
    codebook_service_secret: str = ""
    codebook_timeout_seconds: float = 2.0
    worker_poll_interval_seconds: float = 2.0
    worker_max_attempts: int = 100

    # 知识文件、标签表上传上限及导出行数上限
    upload_max_bytes: int = 50 * 1024 * 1024
    import_max_bytes: int = 20 * 1024 * 1024
    export_max_rows: int = 100_000
    storage_dir: str = "./data/thinktank"
    # Office 预览转出的 PDF 缓存（storage_dir/preview_cache）总量上限，超了从最久没用的删起
    preview_cache_max_bytes: int = 2 * 1024 * 1024 * 1024
    # 预览用 PDF：超过这个大小的先用 Ghostscript 把内嵌图片降到 preview_compress_dpi（Office 转出的一律压），
    # 再用 qpdf 线性化；每个外部命令最长跑 preview_optimize_timeout_seconds 秒，超时就用上一步的结果。
    preview_compress_min_bytes: int = 3 * 1024 * 1024
    preview_compress_dpi: int = 144
    preview_optimize_timeout_seconds: float = 120.0

    # 原服务器 MinIO 对象存储（配置 endpoint 后优先读写 MinIO，未配置则回退本地 storage_dir）
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "tx-bifang-knowledge-emp-service-prod"
    minio_region: str = "us-east-1"
    minio_timeout_seconds: float = 5.0
    minio_io_timeout_seconds: float = 60.0

    def _optional_secret_fields(self) -> set[str]:
        optional: set[str] = set()
        if not self.minio_endpoint.strip():
            optional.add("minio_secret_key")
        if not self.codebook_base_url.strip():
            optional.add("codebook_service_secret")
        return optional

    @model_validator(mode="after")
    def _reject_service_demo_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
            for token in (
                self.iam_service_secret,
                self.audit_ingest_secret,
                self.codebook_service_secret,
                self.minio_secret_key,
            ):
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用或存储密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 必填项从环境变量读取，mypy 只看到构造参数缺失
