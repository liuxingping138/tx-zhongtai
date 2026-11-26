"""审计事件投递体的组装规则。

这些字段直接落进审计库，改动会影响历史记录的可读性和查询。
"""

from __future__ import annotations

import json
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
        event_meta=EVENT_META,
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


def _wired(repo: _Repo, monkeypatch: pytest.MonkeyPatch, *, status: int = 201) -> AuditEmitter:
    emitter = _emitter()
    emitter._sessions = _Session  # type: ignore[assignment]
    emitter._repo = repo
    transport = httpx.MockTransport(lambda _request: httpx.Response(status, json={"code": "OK"}))
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
@pytest.mark.parametrize(("status", "attempts"), [(422, 3), (400, 3), (413, 3), (401, 1), (403, 1), (503, 1)])
async def test_bad_content_is_parked_at_once_but_auth_and_outages_retry(
    monkeypatch: pytest.MonkeyPatch, status: int, attempts: int
) -> None:
    """内容本身不合格（400/413/422）重试多少次都一样，直接停放；
    401/403（换密钥、容器重建有先后）和 5xx 按次数退避重试。"""

    event = _leased("policy.source.created", {})
    repo = _Repo([event])
    assert await _wired(repo, monkeypatch, status=status).deliver_pending(_Settings()) == 0
    assert repo.retried == [(event.event_id, f"http:{status}", attempts)]


@pytest.mark.asyncio
async def test_lost_lease_is_not_counted_as_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo([_leased("policy.source.created", {})], lease_ok=False)
    assert await _wired(repo, monkeypatch).deliver_pending(_Settings()) == 0


def test_ingest_keeps_extra_next_to_changes_and_stays_under_the_size_limit() -> None:
    """批量操作的 ID 清单放在 extra：有 changes 时也要进审计，太长就截短并注明原数，不能让整条审计被拒收。"""

    from platform_common.audit_emit import ingest_changes

    payload = {
        "actor_id": "u1",
        "actor_name": "张三",
        "target_id": "batch",
        "outcome": "success",
        "request_id": "r1",
        "changes": {"data_status": "人工验证", "rows": 2},
        "record_ids": ["a", "b"],
    }
    assert ingest_changes(payload) == {"data_status": "人工验证", "rows": 2, "record_ids": ["a", "b"]}
    assert ingest_changes({**payload, "changes": {}})["actor_name"] == "张三"
    huge = {**payload, "record_ids": [f"{index:036d}" for index in range(2000)]}
    fitted = ingest_changes(huge)
    assert fitted["record_ids_总数"] == 2000 and len(fitted["record_ids"]) < 2000
    assert len(json.dumps(fitted, ensure_ascii=False).encode()) <= 24_000
    # 只有 changes 没有 extra、或只有 extra 没有 changes，超长时一样要截短。
    huge_only_extra = {**huge, "changes": {}}
    fitted_extra = ingest_changes(huge_only_extra)
    assert (
        fitted_extra["record_ids_总数"] == 2000 and len(json.dumps(fitted_extra, ensure_ascii=False).encode()) <= 24_000
    )
    huge_only_changes = {
        **payload,
        "changes": {"record_ids": huge["record_ids"]},
    }
    huge_only_changes.pop("record_ids")
    fitted_changes = ingest_changes(huge_only_changes)
    assert (
        fitted_changes["record_ids_总数"] == 2000
        and len(json.dumps(fitted_changes, ensure_ascii=False).encode()) <= 24_000
    )


def test_fit_truncates_oversized_strings_nested_dicts_and_many_keys() -> None:
    """顶层没有大列表，而是超长字符串、嵌套字典或大量键时，也必须压回 24KB 以内避免进审计死信。"""

    from platform_common.audit_emit import ingest_changes

    big_str = {"changes": {"file_name": "测" * 20_000, "remark": "长" * 20_000}}
    fitted_str = ingest_changes(big_str)
    assert len(json.dumps(fitted_str, ensure_ascii=False).encode()) <= 24_000
    assert "…(共20000字)" in fitted_str["file_name"]

    nested = {"changes": {"diff": {"from": "a" * 30_000, "to": "b" * 30_000}, "items": [{"body": "c" * 30_000}]}}
    fitted_nested = ingest_changes(nested)
    assert len(json.dumps(fitted_nested, ensure_ascii=False).encode()) <= 24_000
    assert fitted_nested["diff"]["from"].startswith("a")

    many_keys = {"changes": {f"field_{idx:04d}": "v" * 200 for idx in range(500)}}
    fitted_many = ingest_changes(many_keys)
    assert len(json.dumps(fitted_many, ensure_ascii=False).encode()) <= 24_000
    assert fitted_many["_已截断"] is True


@pytest.mark.asyncio
async def test_delivered_events_older_than_retention_are_purged_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """已投递的出站记录保留 30 天：审计服务早已入库，这里永不删除只会越积越多。分批删、每批一个事务。"""

    from platform_common import audit_emit

    calls: list[datetime] = []
    batches = iter([audit_emit.PURGE_BATCH, 12])

    class _PurgingRepo(_Repo):
        async def purge_delivered(self, session: Any, *, before: datetime, limit: int = 5000) -> int:
            calls.append(before)
            return next(batches)

    emitter = _emitter()
    emitter._sessions = _Session  # type: ignore[assignment]
    emitter._repo = _PurgingRepo([])
    assert await emitter.purge_delivered(now=OCCURRED) == audit_emit.PURGE_BATCH + 12
    assert calls == [OCCURRED - audit_emit.OUTBOX_RETENTION] * 2


@pytest.mark.asyncio
async def test_emitter_reuses_pooled_http_client_and_closes_on_loop_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    created_clients: list[httpx.AsyncClient] = []
    transport = httpx.MockTransport(lambda _request: httpx.Response(201, json={"code": "OK"}))
    real_client = httpx.AsyncClient

    def _client(**kwargs: Any) -> httpx.AsyncClient:
        client = real_client(transport=transport, **kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    emitter = _emitter()
    emitter._sessions = _Session  # type: ignore[assignment]
    emitter._repo = _Repo([_leased("policy.source.created", {})])

    assert await emitter.deliver_pending(_Settings()) == 1
    assert await emitter.deliver_pending(_Settings()) == 1
    assert len(created_clients) == 1 and not created_clients[0].is_closed

    stop = asyncio.Event()
    stop.set()
    await emitter.outbox_loop(stop, _Settings())
    assert created_clients[0].is_closed
    assert emitter._client is None
