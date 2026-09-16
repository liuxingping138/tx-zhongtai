from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.application.event_map import map_outbox_to_ingest
from app.application.outbox_policy import next_retry_delay, next_status, should_park
from app.application.redact import redact
from app.domain.enums import OutboxStatus
from app.domain.models import OutboxEvent


def test_backoff_and_park() -> None:
    assert next_retry_delay(attempts=1, base_seconds=2, cap_seconds=300).total_seconds() == 2
    assert next_retry_delay(attempts=4, base_seconds=2, cap_seconds=300).total_seconds() == 16
    assert next_retry_delay(attempts=20, base_seconds=2, cap_seconds=10).total_seconds() == 10
    assert should_park(attempts=8, max_attempts=8) is True
    assert next_status(attempts=3, max_attempts=8) == OutboxStatus.FAILED
    assert next_status(attempts=8, max_attempts=8) == OutboxStatus.DEAD


def test_map_login_and_redact_password() -> None:
    event = OutboxEvent(
        event_id=uuid.uuid4(),
        event_type="auth.login.succeeded",
        schema_version=1,
        payload={
            "actor_id": "u1",
            "actor_name": "管理员",
            "username": "admin",
            "password": "should-not-leak",
            "outcome": "success",
            "request_id": "r1",
        },
        status=OutboxStatus.PENDING,
        attempts=0,
        created_at=datetime.now(UTC),
    )
    body = map_outbox_to_ingest(event)
    assert body["module_code"] == "auth"
    assert body["action_code"] == "login"
    assert body["actor_name_snapshot"] == "管理员"
    assert "source_service" not in body
    assert body["changes"]["password"] == "***REDACTED***"
    assert redact({"temporary_password": "x"})["temporary_password"] == "***REDACTED***"


def test_map_unknown_event_type_keeps_type() -> None:
    event = OutboxEvent(
        event_id=uuid.uuid4(),
        event_type="custom.future.event",
        schema_version=1,
        payload={"outcome": "success"},
        status=OutboxStatus.PENDING,
        attempts=0,
        created_at=datetime.now(UTC),
    )
    body = map_outbox_to_ingest(event)
    assert body["module_code"] == "iam"
    assert body["action_code"] == "custom.future.event"
