from __future__ import annotations

from typing import Any

import pytest
from platform_common.actors import Actor

from app.application import scenario_sync
from app.domain.scenario_codes import CodeBook, ScenarioItem

TRAFFIC = ("交通行业", "交通运输、仓储和邮政业", "道路运输")
CAR = ("交通行业", "交通运输、仓储和邮政业", "汽车制造业")
GENERAL = ("交通行业", "", "")
# 线上码表里的真实样例：行业编码 8 位 + 场景编码 12 位，各级号全局唯一。
ROWS = [
    ("01010300", TRAFFIC, "234569261000", ("车路云", "车路协同", "5G 全息路况出行服务")),
    ("01010900", CAR, "234569261000", ("车路云", "车路协同", "5G 全息路况出行服务")),
    ("01010300", TRAFFIC, "024037000000", ("交通数字化管理", "交通行业内部管理与运营", "")),
    ("01010300", TRAFFIC, "247000000000", ("物联网", "", "")),
    ("01010300", TRAFFIC, "100580000000", ("某一级", "某二级", "")),
    # 只挂在一级行业下的通用场景
    ("01000000", GENERAL, "221549000000", ("视联网", "千里眼", "")),
]


def test_existing_scenarios_keep_their_codes() -> None:
    book = CodeBook.from_rows(ROWS)
    codes, created = book.assign(ScenarioItem(CAR, ("车路云", "车路协同", "5G 全息路况出行服务")))
    assert (codes.industry_scenario_code, created) == ("01010900234569261000", False)


def test_new_levels_take_the_next_global_number_and_reuse_known_parents() -> None:
    book = CodeBook.from_rows(ROWS)
    # 一级、二级都已有，只有三级是新的：三级号取全局最大 261 + 1。
    codes, created = book.assign(ScenarioItem(TRAFFIC, ("车路云", "车路协同", "隧道智能巡检")))
    assert (codes.scenario_code, codes.industry_code, created) == ("234569262000", "01010300", True)
    # 全新的一级场景：一级号 247 + 1；二级号 580 + 1；没有三级记 000。
    codes, _ = book.assign(ScenarioItem(TRAFFIC, ("低空经济", "无人机物流", "")))
    assert codes.scenario_code == "248581000000"
    # 同一批里重复出现的新场景拿到同一个编码，不会再分配新号。
    again, created = book.assign(ScenarioItem(TRAFFIC, ("低空经济", "无人机物流", "")))
    assert (again.scenario_code, created) == ("248581000000", False)


def test_general_scenarios_are_found_by_the_first_level_industry() -> None:
    book = CodeBook.from_rows(ROWS)
    # AI 按政策把行业填到了三级，码表里这个场景只挂在一级行业下：用那一行的编码，不新建。
    codes, created = book.assign(ScenarioItem(TRAFFIC, ("视联网", "千里眼", "")))
    assert (codes.industry_scenario_code, created) == ("01000000221549000000", False)
    assert book.lookup(ScenarioItem(("医卫行业", "卫生", "卫生"), ("视联网", "千里眼", ""))) is None


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (ScenarioItem(TRAFFIC, ("车路云", "绿色算力（新增）", "")), "带「（新增）」"),
        (ScenarioItem(("新行业", "", ""), ("车路云", "", "")), "不在行业场景码表里"),
        (ScenarioItem(TRAFFIC, ("", "", "")), "一级场景为空"),
        (ScenarioItem(TRAFFIC, ("车路云", "", "某三级")), "没有二级场景"),
    ],
)
def test_items_that_cannot_be_coded_are_rejected_with_a_reason(item: ScenarioItem, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        CodeBook.from_rows(ROWS).assign(item)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None


async def test_sync_writes_only_new_scenarios_and_reports_each_item(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rows(_session: Any) -> list[Any]:
        return ROWS

    events: list[dict[str, Any]] = []

    async def nothing(_session: Any) -> None:
        return None

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(scenario_sync.repo, "scenario_codes", rows)
    monkeypatch.setattr(scenario_sync.repo, "lock_scenario_codes", nothing)
    monkeypatch.setattr(scenario_sync, "enqueue_event", record)
    session = _Session()
    names = ("industry_l1", "industry_l2", "industry_l3", "scenario_l1_name", "scenario_l2_name", "scenario_l3_name")
    items = [
        {
            "key": "k1",
            **dict(zip(names, (*TRAFFIC, "车路云", "车路协同", "隧道智能巡检"), strict=True)),
            "source_policy": "某政策",
        },
        {"key": "k2", **dict(zip(names, (*CAR, "车路云", "车路协同", "5G 全息路况出行服务"), strict=True))},
        {"key": "k3", **dict(zip(names, ("新行业", "", "", "车路云", "", ""), strict=True))},
    ]
    results = await scenario_sync.sync(session, Actor(id="policy-service", name="张三"), items)  # type: ignore[arg-type]
    assert [(item["key"], item["created"], item["industry_scenario_code"]) for item in results] == [
        ("k1", True, "01010300234569262000"),
        ("k2", False, "01010900234569261000"),
        ("k3", False, ""),
    ]
    assert "不在行业场景码表里" in results[2]["error"]
    added = session.added[0]
    # 来源记在自己的两列里，场景来源、三级场景描述留给业务填。
    assert (added.is_new_scenario, added.source_policy, added.created_by_name) == ("是", "某政策", "张三")
    assert (added.scenario_source, added.scenario_l3_desc) == ("", "")
    assert len(session.added) == 1 and events[0]["extra"] == {"items": 3, "created": 1}
    lookups = await scenario_sync.lookup(session, items[1:])  # type: ignore[arg-type]
    assert [item["scenario_code"] for item in lookups] == ["234569261000", ""]
