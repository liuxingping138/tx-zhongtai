"""服务配置基类。

各服务应继承 `BaseServiceSettings` 并按需追加字段，使用 `pydantic-settings`
从环境变量 / `.env` 加载配置，启动时即完成校验（缺失必要配置直接失败退出）。
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import unquote, urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEMO_SECRET_MARKERS = ("dev-", "example", "changeme", "test-secret")


def _looks_demo(value: str) -> bool:
    return any(marker in value.lower() for marker in _DEMO_SECRET_MARKERS)


def _url_password(url: str) -> str:
    """连接串里的口令（postgresql+asyncpg://用户:口令@主机/库）。口令拼在连接串里，按字段名查不到它。"""

    return unquote(urlsplit(url).password or "")


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
        """生产环境拒绝示例密钥：字段名带 secret / key / password 的字符串、dict 型密钥的每个值、
        连接串里的数据库口令都查；带 secret 的密钥还不能是空的（空着的话服务间调用、审计投递全部 401）。"""

        if self.environment != Environment.PRODUCTION:
            return self
        for field_name in type(self).model_fields:
            for label, value in self._secret_values(field_name):
                if _looks_demo(value):
                    raise ValueError(f"生产环境配置项 {label} 看起来是示例/演示密钥，拒绝启动，请配置真实密钥。")
                if not value and "secret" in field_name:
                    raise ValueError(f"生产环境配置项 {label} 是空的，拒绝启动，请配置真实密钥。")
        return self

    def _secret_values(self, field_name: str) -> list[tuple[str, str]]:
        value = getattr(self, field_name, None)
        if "database_url" in field_name:
            return [(f"{field_name} 里的口令", _url_password(value))] if isinstance(value, str) and value else []
        if not any(word in field_name for word in ("secret", "key", "password")):
            return []
        if isinstance(value, dict):
            if not value:
                return [(field_name, "")]
            return [(f"{field_name}[{name}]", str(item)) for name, item in value.items()]
        return [(field_name, value)] if isinstance(value, str) else []
