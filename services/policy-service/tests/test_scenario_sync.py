from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.actors import Actor

from app.common import internal_clients
from app.policy.application import scenario_sync


def _row(title: str, l3: str, uid: str = "p1") -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        policy_uid=uid,
        policy_title=title,
        opportunity_type="新增需求",
        relation_key=f"{uid}新:交通行业/{l3}新增需求",
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
    monkeypatch.setattr(scenario_sync.repo, "existing_relation_keys", _none_taken)
    monkeypatch.setattr(internal_clients, "codebook", codebook)
    monkeypatch.setattr(scenario_sync, "enqueue_event", record)
    result = await scenario_sync.sync(object(), Actor(id="u1", name="张三"))  # type: ignore[arg-type]
    assert (result["synced"], result["created"]) == (1, 1)
    assert result["failed"] == [{"policy_title": "行业对不上的政策", "reason": "行业不在码表里"}]
    assert result["failed_total"] == 1
    assert (good.industry_scenario_code, good.version, good.updated_by_name) == ("01010300234569262000", 2, "张三")
    # 关联主键换成编码形式，和导入、重新解读按编码算出来的一致。
    assert good.relation_key == "p101010300234569262000新增需求"
    assert good.scenario_synced_at is not None and bad.scenario_synced_at is None
    item = sent[0]["items"][0]
    assert (item["scenario_l3_name"], item["source_policy"]) == ("隧道智能巡检", "隧道巡检方案")
    assert events[0]["extra"] == {"synced": 1, "created": 1, "failed": 1}


async def _none_taken(*_: Any) -> set[str]:
    return set()


async def test_sync_leaves_a_row_alone_when_it_would_duplicate_another(monkeypatch: pytest.MonkeyPatch) -> None:
    """码表里本来就有这个场景，同一政策另有一行指向它、机会类型也一样：两行讲的是同一件事。
    这一行不回填、写进失败清单让人核对，不替人删数据，也不撞关联主键唯一约束。"""

    row = _row("隧道巡检方案", "隧道智能巡检")
    code = "01010300234569262000"

    async def rows(*_: Any) -> list[Any]:
        return [row]

    async def codebook(*_: Any, **__: Any) -> list[dict[str, Any]]:
        codes = {"industry_code": code[:8], "scenario_code": code[8:], "industry_scenario_code": code}
        return [{"key": str(row.id), **codes, "created": False, "error": ""}]

    async def taken(_session: Any, keys: list[str]) -> set[str]:
        return set(keys)

    async def record(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(scenario_sync.repo, "unsynced_new_scenarios", rows)
    monkeypatch.setattr(scenario_sync.repo, "existing_relation_keys", taken)
    monkeypatch.setattr(internal_clients, "codebook", codebook)
    monkeypatch.setattr(scenario_sync, "enqueue_event", record)
    result = await scenario_sync.sync(object(), Actor(id="u1", name="张三"))  # type: ignore[arg-type]
    assert result["synced"] == 0 and result["failed"][0]["reason"] == scenario_sync.SAME_ROW
    assert (row.industry_scenario_code, row.scenario_synced_at, row.version) == ("", None, 1)


async def test_nothing_pending_does_not_call_the_codebook(monkeypatch: pytest.MonkeyPatch) -> None:
    async def none(*_: Any) -> list[Any]:
        return []

    async def boom(*_: Any, **__: Any) -> Any:
        raise AssertionError("不该调用码表服务")

    monkeypatch.setattr(scenario_sync.repo, "unsynced_new_scenarios", none)
    monkeypatch.setattr(internal_clients, "codebook", boom)
    assert await scenario_sync.sync(object(), Actor(id="u1", name="张三")) == {
        "synced": 0,
        "created": 0,
        "failed": [],
        "failed_total": 0,
    }  # type: ignore[arg-type]
