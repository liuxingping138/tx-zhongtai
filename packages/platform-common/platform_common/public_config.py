"""只输出白名单里的非敏感运行参数。不要把整份环境或密钥打出来。"""

from __future__ import annotations

import json
from typing import Any

_SECRET_MARKERS = ("password", "secret", "database_url", "redis_url")

PUBLIC_FIELDS: dict[str, tuple[str, ...]] = {
    "iam": (
        "environment",
        "cookie_secure",
        "access_token_ttl_seconds",
        "refresh_reuse_grace_seconds",
        "login_max_failures",
        "login_max_failures_per_ip",
        "login_lockout_seconds",
        "session_retention_days",
        "worker_lease_seconds",
    ),
    "audit": ("environment", "retention_days"),
    "codebook": ("environment", "import_max_bytes", "export_max_rows"),
    "ai": ("environment", "upload_max_bytes", "batch_concurrency", "batch_max_running", "batch_stale_seconds"),
    "policy": (
        "environment",
        "import_max_bytes",
        "export_max_rows",
        "crawler_sync_days",
        "crawler_backfill_days",
        "crawler_health_normal_days",
        "crawler_health_watch_days",
    ),
}


def public_settings(settings: object, service: str) -> dict[str, Any]:
    names = PUBLIC_FIELDS[service]
    data: dict[str, Any] = {}
    for name in names:
        lowered = name.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            raise ValueError(f"白名单含敏感字段 {name}")
        value = getattr(settings, name)
        data[name] = value.value if hasattr(value, "value") else value
    return data


def dump_public_settings(settings: object, service: str) -> str:
    return json.dumps(public_settings(settings, service), ensure_ascii=False, sort_keys=True)
