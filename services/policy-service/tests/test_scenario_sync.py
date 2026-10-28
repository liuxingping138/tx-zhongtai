from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.actors import Actor

from app.common import internal_clients
from app.policy.application import scenario_sync


def _row(title: str, l3: str) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        policy_title=title,
        industry_l1="交通行业",
        industry_l2="交通运输、仓储和邮政业",
        industry_l3="道路运输",
        scenario_l1_name="车路云",
        scenario_l2_name="车路协同",
        scenario_l3_name=l3,
        industry_code="",
        scenario_code="",
        industry_scenario_code="",
        scenario_synced_at=None,
        version=1,
        updated_at=None,
        updated_by_id="",
        updated_by_name="",
    )


async def test_sync_fills_codes_back_and_explains_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    good, bad = _row("隧道巡检方案", "隧道智能巡检"), _row("行业对不上的政策", "某三级")
    sent: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    async def rows(*_: Any) -> list[Any]:
        return [good, bad]

    async def codebook(method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        sent.append(kwargs["json"])
        return [
            {
                "key": str(good.id),
                "industry_code": "01010300",
                "scenario_code": "234569262000",
                "industry_scenario_code": "01010300234569262000",
                "created": True,
                "error": "",
            },
            {
                "key": str(bad.id),
                "industry_code": "",
                "scenario_code": "",
                "industry_scenario_code": "",
                "error": "行业不在码表里",
            },
        ]

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(scenario_sync.repo, "unsynced_new_scenarios", rows)
    monkeypatch.setattr(internal_clients, "codebook", codebook)
    monkeypatch.setattr(scenario_sync, "enqueue_event", record)
    result = await scenario_sync.sync(object(), Actor(id="u1", name="张三"))  # type: ignore[arg-type]
    assert (result["synced"], result["created"]) == (1, 1)
    assert result["failed"] == [{"policy_title": "行业对不上的政策", "reason": "行业不在码表里"}]
    assert (good.industry_scenario_code, good.version, good.updated_by_name) == ("01010300234569262000", 2, "张三")
    assert good.scenario_synced_at is not None and bad.scenario_synced_at is None
    item = sent[0]["items"][0]
    assert (item["scenario_l3_name"], item["source_policy"]) == ("隧道智能巡检", "隧道巡检方案")
    assert events[0]["extra"] == {"synced": 1, "created": 1, "failed": 1}


async def test_nothing_pending_does_not_call_the_codebook(monkeypatch: pytest.MonkeyPatch) -> None:
    async def none(*_: Any) -> list[Any]:
        return []

    async def boom(*_: Any, **__: Any) -> Any:
        raise AssertionError("不该调用码表服务")

    monkeypatch.setattr(scenario_sync.repo, "unsynced_new_scenarios", none)
    monkeypatch.setattr(internal_clients, "codebook", boom)
    assert await scenario_sync.sync(object(), Actor(id="u1", name="张三")) == {"synced": 0, "created": 0, "failed": []}  # type: ignore[arg-type]
