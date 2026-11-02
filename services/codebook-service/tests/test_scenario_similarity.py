from __future__ import annotations

from typing import Any

import pytest

from app.application import scenario_sync
from app.domain.scenario_similarity import ScenarioNodes, similarity, similarity_level

AIR = ("交通行业", "交通运输、仓储和邮政业", "航空")
ROAD = ("交通行业", "交通运输、仓储和邮政业", "道路运输")
DESCS = ("", "", "")
# 码表按客群重复：同一路径出现两次，节点只算一次
ROWS = [
    (AIR, ("智慧航空", "智慧空侧", "行李自动化"), DESCS, "行李自动化通过……"),
    (AIR, ("智慧航空", "智慧空侧", "低空通讯"), DESCS, ""),
    (AIR, ("智慧航空", "智慧航站楼", "统一联动安防"), DESCS, ""),
    (AIR, ("智慧航空", "智慧航站楼", "统一联动安防"), DESCS, ""),
    (AIR, ("智慧航空", "智慧陆侧", ""), ("", "陆侧描述", ""), ""),
    (ROAD, ("智慧交通工程建设", "交通工程建设信息化", ""), DESCS, "交通工程建设信息化通过构建工程管理云平台"),
    (("医卫行业", "卫生", "卫生"), ("基层医卫", "县域医共体", ""), DESCS, ""),
]


@pytest.mark.parametrize(
    ("a", "b", "level"),
    [
        ("县域医共体信息平台", "县域医共体", "高"),  # 完整包含
        ("智慧河湖长制", "智慧河湖", "高"),
        ("AI 辅助审方", "AI辅助诊疗", "中"),
        ("智慧航空", "智慧水务", "无"),  # 只共用「智慧」
        ("绿色算力中心协同", "算力调度平台", "无"),
    ],
)
def test_similarity_levels(a: str, b: str, level: str) -> None:
    assert similarity_level(similarity(a, b)) == level


def test_short_common_words_do_not_count_as_containment() -> None:
    assert similarity("平台", "算力调度平台") < 0.35


def test_siblings_list_what_already_sits_under_the_same_parent() -> None:
    nodes = ScenarioNodes.from_rows(ROWS)
    assert nodes.siblings(("智慧航空", "智慧机场工程建设管理"), []) == [
        {"name": "智慧空侧", "children": 2},
        {"name": "智慧航站楼", "children": 1},
        {"name": "智慧陆侧", "children": 0},
    ]
    # 新的一级场景：和同一个一级行业下已有的一级场景比
    assert [item["name"] for item in nodes.siblings(("中医药数智化",), ["医卫行业"])] == ["基层医卫"]


def test_similar_returns_existing_nodes_of_any_level_with_description() -> None:
    nodes = ScenarioNodes.from_rows(ROWS)
    found = nodes.similar(("基层医卫", "县域医共体信息平台"))
    assert found[0]["path"] == ["基层医卫", "县域医共体"] and found[0]["level"] == "高"
    assert all(item["path"] != ["智慧航空", "智慧陆侧"] for item in nodes.similar(("智慧航空", "智慧陆侧")))
    assert nodes.nodes[("智慧航空", "智慧陆侧")].desc == "陆侧描述"
    assert nodes.industries_of(("智慧航空",)) == ["交通行业/交通运输、仓储和邮政业/航空"]


async def test_context_answers_each_item(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rows(_session: Any) -> list[Any]:
        return ROWS

    monkeypatch.setattr(scenario_sync.repo, "scenario_nodes", rows)
    items = [
        {"key": "a", "path": ["基层医卫", "县域医共体信息平台", ""], "industry_l1": ["医卫行业"]},
        {"key": "b", "path": []},
    ]
    out = await scenario_sync.context(None, items)  # type: ignore[arg-type]  # 只用到打桩的仓储
    assert (out[0]["key"], out[0]["best_level"], [s["name"] for s in out[0]["siblings"]]) == ("a", "高", ["县域医共体"])
    assert out[1] == {"key": "b", "siblings": [], "similar": [], "industries": [], "best_level": "无"}
