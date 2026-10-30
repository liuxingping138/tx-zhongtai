"""Outbox 投递：成功回写、重复事件计数、网络与 HTTP 失败的重试/封存，以及租约被别人接走时不覆盖。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from platform_common.clock import utcnow

from app.application import outbox_delivery as module
from app.application.outbox_delivery import DeliveryCounters

SETTINGS = SimpleNamespace(
    audit_ingest_secret="secret",
    worker_batch_size=10,
    worker_lease_seconds=30,
    worker_max_attempts=3,
    worker_backoff_base_seconds=2,
    worker_backoff_cap_seconds=60,
)


class _Db:
    def __init__(self) -> None:
        self.commit = AsyncMock()

    async def __aenter__(self) -> _Db:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _event(**overrides: Any) -> SimpleNamespace:
    base = {"event_id": uuid.uuid4(), "lease_until": utcnow() + timedelta(seconds=30), "attempts": 1}
    return SimpleNamespace(**(base | overrides))


class _Client:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.sent: list[dict[str, Any]] = []

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        self.sent.append({"url": url, "json": json, "headers": headers})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(delivered_ok=True, retry_ok=True, retry_args=None)

    async def mark_retry(_s: object, event_id: object, lease: object, **kwargs: Any) -> bool:
        state.retry_args = kwargs
        return state.retry_ok

    monkeypatch.setattr(module, "SessionLocal", _Db)
    monkeypatch.setattr(module, "map_outbox_to_ingest", lambda event: {"event_id": str(event.event_id)})
    monkeypatch.setattr(module.outbox_repo, "mark_delivered", AsyncMock(side_effect=lambda *_: state.delivered_ok))
    monkeypatch.setattr(module.outbox_repo, "mark_retry", mark_retry)
    for name in ("delivered", "duplicate", "retried", "parked", "lease_lost"):
        monkeypatch.setattr(DeliveryCounters, name, 0)
    return state


def _ok(data: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"data": data or {}})


async def test_success_marks_delivered_and_counts(env: SimpleNamespace) -> None:
    client = _Client(_ok())
    await module._deliver_one(SETTINGS, client, _event())  # type: ignore[arg-type]
    assert DeliveryCounters.delivered == 1 and DeliveryCounters.duplicate == 0
    assert client.sent[0]["headers"]["X-Internal-Token"] == "secret"
    assert client.sent[0]["url"] == "/internal/v1/audit/events"


async def test_duplicate_is_counted_and_a_non_json_body_is_tolerated(env: SimpleNamespace) -> None:
    await module._deliver_one(SETTINGS, _Client(_ok({"duplicate": True})), _event())  # type: ignore[arg-type]
    await module._deliver_one(SETTINGS, _Client(httpx.Response(200, text="not json")), _event())  # type: ignore[arg-type]
    assert (DeliveryCounters.delivered, DeliveryCounters.duplicate) == (2, 1)


async def test_lost_lease_on_success_is_not_counted_as_delivered(env: SimpleNamespace) -> None:
    env.delivered_ok = False
    await module._deliver_one(SETTINGS, _Client(_ok()), _event())  # type: ignore[arg-type]
    assert (DeliveryCounters.delivered, DeliveryCounters.lease_lost) == (0, 1)


async def test_event_without_a_lease_is_skipped(env: SimpleNamespace) -> None:
    client = _Client(_ok())
    await module._deliver_one(SETTINGS, client, _event(lease_until=None))  # type: ignore[arg-type]
    assert client.sent == []


async def test_network_error_schedules_a_retry(env: SimpleNamespace) -> None:
    await module._deliver_one(SETTINGS, _Client(httpx.ConnectError("down")), _event(attempts=1))  # type: ignore[arg-type]
    assert env.retry_args["status"] == "failed"
    assert env.retry_args["error_message"] == "network:ConnectError"
    assert env.retry_args["next_retry_at"] is not None
    assert DeliveryCounters.retried == 1


async def test_server_error_retries_until_the_attempt_budget_then_parks(env: SimpleNamespace) -> None:
    await module._deliver_one(SETTINGS, _Client(httpx.Response(503)), _event(attempts=2))  # type: ignore[arg-type]
    assert env.retry_args["status"] == "failed"
    await module._deliver_one(SETTINGS, _Client(httpx.Response(503)), _event(attempts=3))  # type: ignore[arg-type]
    assert env.retry_args["status"] == "dead" and env.retry_args["next_retry_at"] is None
    assert (DeliveryCounters.retried, DeliveryCounters.parked) == (1, 1)


@pytest.mark.parametrize("status", [400, 413, 422])
async def test_bad_content_parks_immediately(env: SimpleNamespace, status: int) -> None:
    await module._deliver_one(SETTINGS, _Client(httpx.Response(status)), _event(attempts=1))  # type: ignore[arg-type]
    assert env.retry_args["status"] == "dead"
    assert env.retry_args["error_message"] == f"http:{status}"


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_rejection_retries_because_secrets_rotate(env: SimpleNamespace, status: int) -> None:
    """两边换密钥、容器重建有先后，几分钟后就好：直接停放的话，轮换一次密钥就丢一批审计。"""

    await module._deliver_one(SETTINGS, _Client(httpx.Response(status)), _event(attempts=1))  # type: ignore[arg-type]
    assert env.retry_args["status"] == "failed" and env.retry_args["next_retry_at"] is not None


async def test_lost_lease_on_retry_is_only_counted(env: SimpleNamespace) -> None:
    env.retry_ok = False
    await module._deliver_one(SETTINGS, _Client(httpx.Response(500)), _event())  # type: ignore[arg-type]
    assert (DeliveryCounters.retried, DeliveryCounters.lease_lost) == (0, 1)


async def test_claim_and_deliver_delivers_every_claimed_event(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [_event(), _event()]
    claim = AsyncMock(return_value=events)
    monkeypatch.setattr(module.outbox_repo, "claim_batch", claim)
    client = _Client(_ok())
    assert await module.claim_and_deliver(SETTINGS, client) == 2  # type: ignore[arg-type]
    assert DeliveryCounters.delivered == 2
    assert claim.await_args.kwargs == {"limit": 10, "lease": timedelta(seconds=30)}


async def test_metrics_and_replay_delegate_to_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.outbox_repo, "metrics", AsyncMock(return_value={"dead_count": 1}))
    replayed = AsyncMock(return_value=5)
    monkeypatch.setattr(module.outbox_repo, "replay", replayed)
    assert await module.metrics(object()) == {"dead_count": 1}  # type: ignore[arg-type]
    assert await module.replay(object(), event_id=None, event_type="x", statuses=("dead",), limit=7) == 5  # type: ignore[arg-type]
    assert replayed.await_args.kwargs["limit"] == 7


async def test_delivered_events_are_purged_after_retention_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """已投递的出站记录保留 30 天，分批删：原来永不删除，iam_outbox 只增不减。"""

    now = utcnow()
    batches = iter([module.PURGE_BATCH, 3])
    cutoffs: list[Any] = []

    async def purge(_session: Any, *, before: Any, limit: int) -> int:
        cutoffs.append((before, limit))
        return next(batches)

    monkeypatch.setattr(module, "SessionLocal", _Db)
    monkeypatch.setattr(module.outbox_repo, "purge_delivered", purge)
    assert await module.purge_delivered(now=now) == module.PURGE_BATCH + 3
    assert cutoffs == [(now - module.OUTBOX_RETENTION, module.PURGE_BATCH)] * 2
