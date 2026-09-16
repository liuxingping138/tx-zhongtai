from __future__ import annotations

import os

os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://audit_app:test@localhost:5432/audit_db")
os.environ.setdefault("AUDIT_INTERNAL_CALLER_SECRETS", '{"iam-service":"unit-test-token"}')

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_ingest_rejects_missing_internal_credentials() -> None:
    client = TestClient(app)
    resp = client.post(
        "/internal/v1/audit/events",
        json={
            "event_id": "11111111-1111-1111-1111-111111111111",
            "occurred_at": "2026-01-01T00:00:00Z",
            "outcome": "success",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_UNAUTHENTICATED"


def test_query_rejects_anonymous() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_UNAUTHENTICATED"
