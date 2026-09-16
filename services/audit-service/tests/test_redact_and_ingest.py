from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api.schemas import IngestRequest
from app.application.ingest import build_event, payload_bytes
from app.application.redact import redact


def test_redact_nested_secrets() -> None:
    payload = redact(
        {
            "username": "alice",
            "password": "secret",
            "nested": {"refresh_token": "abc", "ok": 1},
        }
    )
    assert payload["username"] == "alice"
    assert payload["password"] == "***REDACTED***"
    assert payload["nested"]["refresh_token"] == "***REDACTED***"
    assert payload["nested"]["ok"] == 1


def test_build_event_uses_credential_source_not_body() -> None:
    body = IngestRequest(
        event_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        outcome="success",
        summary="x",
    )
    event = build_event("iam-service", body)
    assert event.source_service == "iam-service"
    assert "forged" not in event.source_service


def test_payload_size_counts_json_bytes() -> None:
    body = IngestRequest(event_id=uuid.uuid4(), occurred_at=datetime.now(UTC), outcome="success", summary="你好")
    assert payload_bytes(body) > 0
