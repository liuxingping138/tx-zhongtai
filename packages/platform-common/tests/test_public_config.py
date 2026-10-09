"""运行参数检查只包含白名单字段。"""

from __future__ import annotations

import pytest

from platform_common.public_config import PUBLIC_FIELDS, public_settings


class _Settings:
    environment = "development"
    cookie_secure = False
    access_token_ttl_seconds = 28800
    refresh_reuse_grace_seconds = 30
    login_max_failures = 5
    login_max_failures_per_ip = 20
    login_lockout_seconds = 300
    session_retention_days = 30
    worker_lease_seconds = 30
    database_url = "postgresql://secret"
    audit_ingest_secret = "hidden"


def test_public_settings_omit_secrets() -> None:
    shown = public_settings(_Settings(), "iam")
    assert shown["cookie_secure"] is False
    assert shown["login_max_failures"] == 5
    assert "database_url" not in shown
    assert "audit_ingest_secret" not in shown
    blob = str(shown)
    assert "postgresql://secret" not in blob
    assert "hidden" not in blob


def test_allowlist_rejects_secret_names() -> None:
    original = PUBLIC_FIELDS["iam"]
    PUBLIC_FIELDS["iam"] = ("database_url",)
    try:
        with pytest.raises(ValueError, match="敏感字段"):
            public_settings(_Settings(), "iam")
    finally:
        PUBLIC_FIELDS["iam"] = original
