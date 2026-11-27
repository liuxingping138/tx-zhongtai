"""thinktank-service 配置。环境变量前缀 `THINKTANK_`。"""

from __future__ import annotations

import ipaddress
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
    # 上传 PDF / Office 后在后台先做好预览缓存，第一个打开的人也不用等转码、压缩；转码名额被占着就不做
    preview_warmup_on_upload: bool = True

    # 原服务器 MinIO 对象存储（配置 endpoint 后优先读写 MinIO，未配置则回退本地 storage_dir）
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "tx-bifang-knowledge-emp-service-prod"
    minio_region: str = "us-east-1"
    minio_timeout_seconds: float = 5.0
    minio_io_timeout_seconds: float = 60.0

    # 智库只在公司网络里能用：放行公司出口 IP（逗号分隔，可写网段）和管理员在「访问白名单」里开通、还没到期的 IP。
    # 关掉（network_guard_enabled=false）只给单测、P6 这类从容器网络里访问的环境用。
    network_guard_enabled: bool = True
    office_networks: str = "1.119.196.74"
    # 白名单一次最长开多少天：到期要管理员续，免得临时开的口子变成永久的。
    whitelist_max_days: int = 365

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

    @model_validator(mode="after")
    def _check_office_networks(self) -> Settings:
        for item in self.office_network_items():
            try:
                ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError(f"THINKTANK_OFFICE_NETWORKS 里的「{item}」不是有效的 IP 或网段") from exc
        if self.network_guard_enabled and not self.office_network_items():
            raise ValueError("开启了智库网络限制但 THINKTANK_OFFICE_NETWORKS 为空，所有人都会被拦在外面")
        if self.whitelist_max_days < 1:
            raise ValueError("THINKTANK_WHITELIST_MAX_DAYS 至少为 1")
        return self

    def office_network_items(self) -> list[str]:
        return [item for item in self.office_networks.replace(";", ",").replace(" ", ",").split(",") if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 必填项从环境变量读取，mypy 只看到构造参数缺失
