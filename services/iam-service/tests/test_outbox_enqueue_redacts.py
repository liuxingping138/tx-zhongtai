"""入队即脱敏。Outbox 落在 iam_db 里，只在投递时脱敏挡不住业务库留痕。"""

from __future__ import annotations

from typing import Any

import pytest

from app.repositories.outbox import enqueue


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, instance: Any) -> None:
        self.added.append(instance)


@pytest.mark.asyncio
async def test_enqueue_redacts_before_persisting() -> None:
    session = _FakeSession()
    event = await enqueue(
        session,  # type: ignore[arg-type]
        event_type="auth.login.succeeded",
        payload={
            "username": "admin",
            "password": "should-not-leak",
            "detail": {"csrf_token": "should-not-leak"},
            "outcome": "success",
        },
    )

    assert session.added == [event]
    assert event.payload["password"] == "***REDACTED***"
    assert event.payload["detail"]["csrf_token"] == "***REDACTED***"
    assert event.payload["username"] == "admin"
    assert event.payload["outcome"] == "success"
