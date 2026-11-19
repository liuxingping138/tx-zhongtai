"""招中标源库配置：本服务没有写库和迁移能力。"""

from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="TENDER_", env_file=".env", extra="ignore")

    service_name: str = "tender-service"
    http_port: int = 8006
    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0
    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    mysql_host: str = ""
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_connect_timeout: int = Field(default=5, ge=1, le=30)
    mysql_read_timeout: int = Field(default=20, ge=1, le=120)
    mysql_count_timeout: int = Field(default=120, ge=1, le=300)
    stats_cache_seconds: int = Field(default=300, ge=1)
    export_max_rows: int = Field(default=50000, ge=1, le=100000)

    @model_validator(mode="after")
    def production_secret(self) -> "Settings":
        bad_secret = not self.iam_service_secret or any(
            marker in self.iam_service_secret.lower() for marker in ("dev-", "example", "changeme", "test-", "p6-only")
        )
        if self.environment == Environment.PRODUCTION and bad_secret:
            raise ValueError("生产环境必须配置有效的招中标内部调用密钥")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
