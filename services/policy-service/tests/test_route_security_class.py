from __future__ import annotations

import os

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "unit-test")

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402


def test_api_routes_declare_security_class() -> None:
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if path.startswith("/health"):
            continue
        if not path.startswith("/api/"):
            continue
        if getattr(route.endpoint, "__security_class__", None) is None:
            methods = ",".join(sorted(route.methods or []))
            missing.append(f"{methods} {path}")
    assert missing == [], f"以下路由未声明安全分类: {missing}"
