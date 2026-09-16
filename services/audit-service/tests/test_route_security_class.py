from __future__ import annotations

import os

os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://audit_app:test@localhost:5432/audit_db")

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402


def test_api_and_internal_routes_declare_security_class() -> None:
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if path.startswith("/health"):
            continue
        if not (path.startswith("/api/") or path.startswith("/internal/")):
            continue
        if getattr(route.endpoint, "__security_class__", None) is None:
            methods = ",".join(sorted(route.methods or []))
            missing.append(f"{methods} {path}")
    assert missing == [], f"以下路由未声明安全分类: {missing}"
