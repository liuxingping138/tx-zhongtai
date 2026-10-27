"""重新打标的请求规则和批量改解读数据状态。仓储和审计用替身；整条重打流程在集成测试里。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError

from app.aitag.application import retag
from app.aitag.domain.rules import drop_notes
from app.aitag.repositories import source
from app.policy.application import interpretation_status

ACTOR = SimpleNamespace(id="u1", name="管理员")
EARLIER = datetime(2026, 10, 22, 9, tzinfo=UTC)


def test_drop_notes_keeps_other_remarks() -> None:
    remark = "人工备注；AI 解读失败：限流；AI 市场机会失败：超时"
    assert drop_notes(remark, ("AI 解读失败", "AI 市场机会失败")) == "人工备注"
    assert drop_notes(remark, ("AI 市场机会失败",)) == "人工备注；AI 解读失败：限流"
    assert drop_notes("", ("AI 解读失败",)) == ""


def _tag(**values: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "source_content_id": "c1",
        "need_interpret": "是",
        "interpreted_at": EARLIER,
        "opportunity_at": EARLIER,
        "type_retag_at": None,
        "remark": "AI 解读失败：限流",
        "version": 1,
        "updated_at": EARLIER,
    }
    return SimpleNamespace(**(base | values))


@pytest.fixture
def tags(monkeypatch: pytest.MonkeyPatch) -> dict[uuid.UUID, Any]:
    store: dict[uuid.UUID, Any] = {}

    async def by_ids(_session: Any, ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
        return {item_id: store[item_id] for item_id in ids if item_id in store}

    monkeypatch.setattr(retag.repo, "base_tags_by_ids", by_ids)
    monkeypatch.setattr(retag, "enqueue_event", AsyncMock())
    return store


async def test_retag_puts_policies_back_on_the_right_task(tags: dict[uuid.UUID, Any]) -> None:
    ok, manual, not_needed = _tag(), _tag(source_content_id=None), _tag(need_interpret="否")
    tags.update({item.id: item for item in (ok, manual, not_needed)})
    out = await retag.request(None, ACTOR, [ok.id, manual.id, not_needed.id, uuid.uuid4()], "interpret")  # type: ignore[arg-type]
    assert (out["task"], out["queued"]) == ("政策解读", 1)
    assert {item["reason"][:6] for item in out["skipped"]} == {"手工录入或导", "「是否解读」", "政策已被删除"}
    # 回到解读待办，市场机会也要重做；旧的失败说明去掉；不改更新时间（不算人工改过），版本号加一。
    assert (ok.interpreted_at, ok.opportunity_at, ok.remark, ok.version, ok.updated_at) == (None, None, "", 2, EARLIER)
    assert manual.version == 1 and not_needed.interpreted_at == EARLIER


async def test_type_and_opportunity_retags(tags: dict[uuid.UUID, Any]) -> None:
    typed, fresh = _tag(), _tag(interpreted_at=None, opportunity_at=None)
    tags.update({typed.id: typed, fresh.id: fresh})
    await retag.request(None, ACTOR, [typed.id], "type")  # type: ignore[arg-type]
    assert typed.type_retag_at is not None and typed.interpreted_at == EARLIER
    out = await retag.request(None, ACTOR, [typed.id, fresh.id], "opportunity")  # type: ignore[arg-type]
    assert out["queued"] == 1 and out["skipped"][0]["reason"] == "还没解读，先重新解读"
    assert typed.opportunity_at is None and typed.interpreted_at == EARLIER
    with pytest.raises(ApiError, match="不认识的打标步骤"):
        await retag.request(None, ACTOR, [typed.id], "nope")  # type: ignore[arg-type]


def test_read_by_ids_keeps_the_requested_order(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[tuple[str, list[str]]] = []

    class Cursor:
        def execute(self, sql: str, params: list[str]) -> None:
            executed.append((sql, params))

        def fetchall(self) -> list[dict[str, Any]]:
            return [{"content_id": "b"}, {"content_id": "a"}]

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(source, "mysql_connect", lambda _db: Connection())
    rows = source.read_by_ids(["a", "gone", "b"])
    assert [row["content_id"] for row in rows] == ["a", "b"]
    assert "WHERE content_id IN (%s, %s, %s)" in executed[0][0] and "collect_date" in executed[0][0]


async def test_batch_data_status(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = SimpleNamespace(id=uuid.uuid4(), record_id="r1", data_status="待验证", version=1, updated_at=EARLIER)
    done = SimpleNamespace(id=uuid.uuid4(), record_id="r2", data_status="人工验证", version=3, updated_at=EARLIER)
    rows = [pending, done]
    events = AsyncMock()

    async def locked(_session: Any, ids: list[uuid.UUID]) -> list[Any]:
        return [row for row in rows if row.id in ids]

    monkeypatch.setattr(interpretation_status.repo, "get_many_for_update", locked)
    monkeypatch.setattr(interpretation_status, "enqueue_event", events)
    out = await interpretation_status.set_data_status(None, ACTOR, [pending.id, done.id], "人工验证")  # type: ignore[arg-type]
    assert out == {"updated": 1, "unchanged": 1}
    assert (pending.data_status, pending.version, pending.updated_by_name) == ("人工验证", 2, "管理员")
    assert done.version == 3 and events.await_args.kwargs["event_type"] == "policy.interpretation.status_changed"
    with pytest.raises(ApiError, match="数据状态只能是"):
        await interpretation_status.set_data_status(None, ACTOR, [pending.id], "已作废")  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await interpretation_status.set_data_status(None, ACTOR, [pending.id, uuid.uuid4()], "待验证")  # type: ignore[arg-type]


def test_ai_status_filter_finds_failures_and_queues() -> None:
    from sqlalchemy.dialects import postgresql

    from app.policy.domain.fields import AI_STATUS_CHOICES
    from app.policy.repositories import base_tags

    assert set(base_tags.AI_STATUS) == set(AI_STATUS_CHOICES)
    (failed,) = base_tags._conditions({"ai_status": ["类型判断失败", "解读失败"]})
    sql = str(failed.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "AI 类型判断失败%" in sql and "%；AI 解读失败%" in sql and "AI 没有判断出政策类型%" in sql
    assert base_tags._conditions({"ai_status": []}) == []
    with pytest.raises(KeyError):
        base_tags._conditions({"ai_status": ["不存在"]})


def test_ai_status_column_uses_the_filter_rules_failures_first() -> None:
    """列表「打标状态」列和筛选同一套条件：同时符合时先报失败、再报排队；手工录入的行为空。"""

    from app.policy.domain.fields import AI_NOTE_INTERPRET_FAILED, AI_NOTE_TYPE_UNKNOWN, ai_status

    now = datetime.now(UTC)
    ai = {"source_content_id": "c1", "need_interpret": "是", "type_retag_at": None, "remark": ""}

    def status(**overrides: Any) -> str:
        return ai_status(**{**ai, "interpreted_at": now, "opportunity_at": now, **overrides})

    assert status() == "已完成"
    assert status(source_content_id=None) == ""
    assert status(interpreted_at=None, opportunity_at=None) == "待解读"
    assert status(need_interpret="否", interpreted_at=None, opportunity_at=None) == "已完成"
    assert status(opportunity_at=None) == "待补市场机会"
    assert status(type_retag_at=now, interpreted_at=None) == "等待重新判断类型"
    assert status(remark=f"人工备注；{AI_NOTE_INTERPRET_FAILED}：超时", interpreted_at=None) == "解读失败"
    assert status(remark=f"{AI_NOTE_TYPE_UNKNOWN}：数字经济；{AI_NOTE_INTERPRET_FAILED}：超时") == "类型判断失败"
