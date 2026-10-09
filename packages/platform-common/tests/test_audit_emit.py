"""审计事件投递体的组装规则。

这些字段直接落进审计库，改动会影响历史记录的可读性和查询。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from platform_common.audit_emit import AuditEmitter
from platform_common.outbox import OutboxRepository

EVENT_META = {
    "policy.source.created": ("policy.sources", "create", "source", "新增信源"),
    "policy.source.purged": ("policy.sources", "purge", "source", "清空信源表"),
}
OCCURRED = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)


class _Event:
    def __init__(self, event_type: str, payload: dict[str, Any]) -> None:
        self.event_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        self.event_type = event_type
        self.schema_version = 1
        self.created_at = OCCURRED
        self.payload = payload


def _emitter() -> AuditEmitter:
    return AuditEmitter(
        service_name="policy-service",
        log_name="policy",
        event_meta=EVENT_META,
        default_module="policy",
        outbox_model=object,
        session_factory=None,  # type: ignore[arg-type]
        get_settings=lambda: None,  # type: ignore[arg-type,return-value]
    )


def test_known_event_uses_its_mapping() -> None:
    body = _emitter().to_ingest(_Event("policy.source.created", {"actor_name": "张三", "target_id": "abc"}))
    assert body["module_code"] == "policy.sources"
    assert body["action_code"] == "create"
    assert body["target_type"] == "source"
    assert body["summary"] == "新增信源 / 张三 / abc"
    assert body["occurred_at"] == OCCURRED.isoformat()
    assert body["outcome"] == "success"


def test_unknown_event_falls_back_to_default_module() -> None:
    body = _emitter().to_ingest(_Event("policy.brand.new", {}))
    assert body["module_code"] == "policy"
    assert body["action_code"] == "policy.brand.new"
    assert body["target_type"] == "record"


def test_summary_appends_counts_in_fixed_order() -> None:
    body = _emitter().to_ingest(_Event("policy.source.purged", {"actor_name": "张三", "inserted": 5, "deleted": 20002}))
    assert body["summary"] == "清空信源表 / 张三 / 新增5条 / 清空20002条"


def test_zero_counts_are_still_reported() -> None:
    """0 条也要写进摘要：``is not None`` 而不是真值判断。"""

    body = _emitter().to_ingest(_Event("policy.source.created", {"actor_name": "张三", "inserted": 0}))
    assert "新增0条" in body["summary"]


def test_changes_falls_back_to_whole_payload() -> None:
    body = _emitter().to_ingest(_Event("policy.source.created", {"actor_name": "张三", "inserted": 3}))
    assert body["changes"] == {"actor_name": "张三", "inserted": 3}

    with_changes = _emitter().to_ingest(_Event("policy.source.created", {"changes": {"a": 1}}))
    assert with_changes["changes"] == {"a": 1}


def test_target_id_is_stringified_or_none() -> None:
    assert _emitter().to_ingest(_Event("policy.source.created", {"target_id": 42}))["target_id"] == "42"
    assert _emitter().to_ingest(_Event("policy.source.created", {}))["target_id"] is None


# ---- 投递循环：本地异常不能拖住整批，租约失效时不覆盖别人的结果 ----


LEASE = datetime(2026, 9, 24, 1, 0, tzinfo=UTC)


class _Settings:
    audit_ingest_url = "http://audit"
    audit_ingest_secret = "s"
    worker_max_attempts = 3
    worker_poll_interval_seconds = 1.0


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Repo(OutboxRepository):
    def __init__(self, events: list[Any], *, lease_ok: bool = True) -> None:
        self.events = events
        self.lease_ok = lease_ok
        self.delivered: list[Any] = []
        self.retried: list[tuple[Any, str, int]] = []

    async def claim_pending(self, session: Any, **_kwargs: Any) -> list[Any]:
        return self.events

    async def mark_delivered(self, session: Any, event_id: Any, expected_lease: datetime) -> bool:
        assert expected_lease == LEASE
        self.delivered.append(event_id)
        return self.lease_ok

    async def mark_retry(
        self, session: Any, event_id: Any, expected_lease: datetime, *, attempts: int, error: str, max_attempts: int
    ) -> bool:
        assert expected_lease == LEASE
        self.retried.append((event_id, error, attempts))
        return self.lease_ok


def _leased(event_type: str, payload: Any) -> _Event:
    event = _Event(event_type, payload)
    event.event_id = uuid.uuid4()
    event.lease_until = LEASE  # type: ignore[attr-defined]
    event.attempts = 1  # type: ignore[attr-defined]
    return event


def _wired(repo: _Repo, monkeypatch: pytest.MonkeyPatch) -> AuditEmitter:
    emitter = _emitter()
    emitter._sessions = _Session  # type: ignore[assignment]
    emitter._repo = repo
    transport = httpx.MockTransport(lambda _request: httpx.Response(201, json={"code": "OK"}))
    real_client = httpx.AsyncClient

    def _client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return emitter


@pytest.mark.asyncio
async def test_bad_event_is_retried_and_rest_of_batch_still_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    good = _leased("policy.source.created", {"actor_name": "张三"})
    bad = _leased("policy.source.created", {"actor_name": "李四"})
    bad.created_at = None  # type: ignore[assignment]  # to_ingest 调 isoformat() 时抛 AttributeError
    later = _leased("policy.source.created", {"actor_name": "王五"})
    repo = _Repo([good, bad, later])

    delivered = await _wired(repo, monkeypatch).deliver_pending(_Settings())

    assert delivered == 2
    assert repo.delivered == [good.event_id, later.event_id]
    assert repo.retried == [(bad.event_id, "error:AttributeError", 1)]


@pytest.mark.asyncio
async def test_lost_lease_is_not_counted_as_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo([_leased("policy.source.created", {})], lease_ok=False)
    assert await _wired(repo, monkeypatch).deliver_pending(_Settings()) == 0
