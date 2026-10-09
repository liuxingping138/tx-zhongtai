from __future__ import annotations

import os

os.environ.setdefault("IAM_DATABASE_URL", "postgresql+asyncpg://iam_app:test@localhost:5432/iam_db")
os.environ.setdefault("IAM_REDIS_URL", "redis://localhost:6379/0")

from fastapi.testclient import TestClient

from app.main import app


def test_health_live() -> None:
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}


def test_unknown_route_returns_unified_404() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["data"] is None
