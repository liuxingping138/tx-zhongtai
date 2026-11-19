"""BaseServiceSettings 生产密钥校验测试（含子类不覆盖父类校验器的回归测试）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError, model_validator

from platform_common.config import BaseServiceSettings, Environment


class _SampleServiceSettings(BaseServiceSettings):
    database_url: str
    iam_service_secret: str = ""
    optional_endpoint: str = ""
    optional_secret_key: str = ""

    def _optional_secret_fields(self) -> set[str]:
        return {"optional_secret_key"} if not self.optional_endpoint else set()

    @model_validator(mode="after")
    def _reject_service_demo_secrets_in_production(self) -> _SampleServiceSettings:
        return self


def test_production_rejects_demo_database_password_even_with_subclass_validator() -> None:
    with pytest.raises(ValidationError, match="database_url 里的口令"):
        _SampleServiceSettings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://app:dev-only-change-me@postgres:5432/app_db",
            iam_service_secret="real-prod-token-9f8e7d6c",
        )


def test_production_rejects_p6_only_secret() -> None:
    with pytest.raises(ValidationError, match="iam_service_secret"):
        _SampleServiceSettings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://app:real-prod-pass-1234@postgres:5432/app_db",
            iam_service_secret="p6-only-change-me-internal",
        )


def test_production_rejects_empty_required_secret() -> None:
    with pytest.raises(ValidationError, match="iam_service_secret"):
        _SampleServiceSettings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://app:real-prod-pass-1234@postgres:5432/app_db",
            iam_service_secret="",
        )


def test_production_allows_optional_secret_when_disabled_and_requires_when_enabled() -> None:
    ok = _SampleServiceSettings(
        environment=Environment.PRODUCTION,
        database_url="postgresql+asyncpg://app:real-prod-pass-1234@postgres:5432/app_db",
        iam_service_secret="real-prod-token-9f8e7d6c",
        optional_endpoint="",
        optional_secret_key="",
    )
    assert ok.optional_secret_key == ""

    with pytest.raises(ValidationError, match="optional_secret_key"):
        _SampleServiceSettings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://app:real-prod-pass-1234@postgres:5432/app_db",
            iam_service_secret="real-prod-token-9f8e7d6c",
            optional_endpoint="http://minio:9000",
            optional_secret_key="",
        )
