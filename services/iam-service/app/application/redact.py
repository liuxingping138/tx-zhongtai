"""Outbox 投递前脱敏，避免密码、令牌进入审计库。"""

from __future__ import annotations

from typing import Any

_SENSITIVE = {
    "password",
    "old_password",
    "new_password",
    "temporary_password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "set-cookie",
    "secret",
    "private_key",
    "csrf_token",
    "internal_token",
}
_REDACTED = "***REDACTED***"


def redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in _SENSITIVE:
        return _REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
