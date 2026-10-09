"""服务配置基类。

各服务应继承 `BaseServiceSettings` 并按需追加字段，使用 `pydantic-settings`
从环境变量 / `.env` 加载配置，启动时即完成校验（缺失必要配置直接失败退出）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEMO_SECRET_MARKERS = ("dev-", "example", "changeme", "test-secret")


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class BaseServiceSettings(BaseSettings):
    """公共配置基类。生产环境下拒绝明显的示例/演示密钥。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    service_name: str = "service"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _reject_demo_secrets_in_production(self) -> BaseServiceSettings:
        if self.environment != Environment.PRODUCTION:
            return self
        for field_name in self.model_fields:
            if "secret" not in field_name and "key" not in field_name and "password" not in field_name:
                continue
            value = getattr(self, field_name, None)
            if isinstance(value, str) and any(marker in value.lower() for marker in _DEMO_SECRET_MARKERS):
                raise ValueError(f"生产环境配置项 {field_name} 看起来是示例/演示密钥，拒绝启动，请配置真实密钥。")
        return self
