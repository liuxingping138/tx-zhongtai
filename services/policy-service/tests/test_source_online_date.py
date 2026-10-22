"""信源上线时间：爬虫状态改成「已爬」记当天，手填优先，停爬不动；以及勾选多条批量改状态。仓储和审计用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError

from app.policy.application import source_status, sources
from app.policy.domain.models import Source

ACTOR = SimpleNamespace(id="u1", name="测试")
NOW = datetime(2026, 10, 1, tzinfo=UTC)
TODAY = "2026-10-22"


@pytest.mark.parametrize(
    ("old_status", "new_status", "old_date", "new_date", "expected"),
    [
        ("未爬", "已爬", "", "", TODAY),  # 上线：记当天
        ("未爬", "已爬", "2024-01-02", "2024-01-02", TODAY),  # 重新上线：覆盖旧日期
        ("未爬", "已爬", "", "2026-10-20", "2026-10-20"),  # 同时手填了日期：以手填为准
        ("已爬", "未爬", "2024-01-02", "2024-01-02", "2024-01-02"),  # 停爬：上线时间不动
        ("已爬", "已爬", "2024-01-02", "2024-01-02", "2024-01-02"),  # 状态没变
        ("未爬", "暂停", "", "", ""),  # 改成别的状态不算上线
        ("", "已爬", "", "", TODAY),  # 新建时选已爬没填日期
    ],
)
def test_online_date_follows_the_status_change(
    old_status: str, new_status: str, old_date: str, new_date: str, expected: str
) -> None:
    assert source_status.online_date_after(old_status, new_status, old_date, new_date, TODAY) == expected


def _row(**values: Any) -> Source:
    base = {
        "site_name": "某网站",
        "province_name": "北京市",
        "city_name": "北京市",
        "tag": "政策",
        "province_code": "11",
        "city_code": "1101",
        "district_code": "110101",
        "crawler_status": "未爬",
        "online_date": "",
    } | values
    return Source(
        id=uuid.uuid4(),
        internal_id=sources.make_internal_id("某网站", "北京市", "北京市", "政策"),
        site_code="11010100001",
        version=1,
        created_at=NOW,
        created_by_name="a",
        updated_at=NOW,
        updated_by_name="a",
        **base,
    )


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(row=None, rows=[], events=[])
    record = AsyncMock(side_effect=lambda *_a, **k: state.events.append(k))
    for module in (sources, source_status):
        monkeypatch.setattr(module, "beijing_today", lambda: TODAY)
        monkeypatch.setattr(module, "enqueue_event", record)
    monkeypatch.setattr(sources.repo, "get_by_internal_id", AsyncMock(return_value=None))
    monkeypatch.setattr(sources.repo, "get_by_site_code", AsyncMock(return_value=None))
    monkeypatch.setattr(sources.repo, "list_site_codes_for_district", AsyncMock(return_value=[]))
    monkeypatch.setattr(sources.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
    monkeypatch.setattr(sources.repo, "get_many_for_update", AsyncMock(side_effect=lambda *_: state.rows))
    return state


class _Session:
    def __init__(self) -> None:
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        row.id = row.id or uuid.uuid4()


async def test_editing_status_to_crawled_stamps_today(env: SimpleNamespace) -> None:
    env.row = _row(online_date="2024-01-02")
    out = await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 1, "crawler_status": "已爬"})  # type: ignore[arg-type]
    assert out["online_date"] == TODAY
    assert env.events[0]["changes"]["online_date"] == {"from": "2024-01-02", "to": TODAY}


async def test_editing_other_fields_leaves_online_date_alone(env: SimpleNamespace) -> None:
    env.row = _row(crawler_status="已爬", online_date="2024-01-02")
    out = await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 1, "department": "市政府"})  # type: ignore[arg-type]
    assert out["online_date"] == "2024-01-02"


async def test_creating_a_crawled_source_without_a_date_stamps_today(env: SimpleNamespace) -> None:
    data = {"site_name": "某网站", "province_name": "北京市", "district_code": "110101", "crawler_status": "已爬"}
    out = await sources.create_source(_Session(), ACTOR, data)  # type: ignore[arg-type]
    assert out["online_date"] == TODAY


async def test_batch_status_updates_changed_rows_only(env: SimpleNamespace) -> None:
    waiting, live = _row(), _row(crawler_status="已爬", online_date="2024-01-02")
    env.rows = [waiting, live]
    out = await source_status.set_crawler_status(None, ACTOR, [waiting.id, live.id], " 已爬 ")  # type: ignore[arg-type]
    assert out == {"updated": 1, "unchanged": 1}
    assert (waiting.crawler_status, waiting.online_date, waiting.version) == ("已爬", TODAY, 2)
    assert (live.online_date, live.version) == ("2024-01-02", 1)
    assert waiting.updated_by_name == "测试"
    assert [event["event_type"] for event in env.events] == ["policy.source.status_changed"]


async def test_batch_stop_keeps_online_date(env: SimpleNamespace) -> None:
    live = _row(crawler_status="已爬", online_date="2024-01-02")
    env.rows = [live]
    await source_status.set_crawler_status(None, ACTOR, [live.id], "未爬")  # type: ignore[arg-type]
    assert (live.crawler_status, live.online_date) == ("未爬", "2024-01-02")


async def test_batch_rejects_blank_status_and_missing_rows(env: SimpleNamespace) -> None:
    with pytest.raises(ApiError, match="爬虫状态不能为空"):
        await source_status.set_crawler_status(None, ACTOR, [uuid.uuid4()], "  ")  # type: ignore[arg-type]
    env.rows = [_row()]
    with pytest.raises(NotFoundError):
        await source_status.set_crawler_status(None, ACTOR, [env.rows[0].id, uuid.uuid4()], "已爬")  # type: ignore[arg-type]
    assert env.events == []
