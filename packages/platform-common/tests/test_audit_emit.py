"""审计事件投递体的组装规则。

这些字段直接落进审计库，改动会影响历史记录的可读性和查询。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from platform_common.audit_emit import AuditEmitter

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
    body = _emitter().to_ingest(
        _Event("policy.source.purged", {"actor_name": "张三", "inserted": 5, "deleted": 20002})
    )
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
