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
    assert added.enrich_status == "待补充"  # 只有名称，排进 AI 补描述
    assert (added.scenario_source, added.scenario_l3_desc) == ("", "")
    assert len(session.added) == 1 and events[0]["extra"] == {"items": 3, "created": 1}
    lookups = await scenario_sync.lookup(session, items[1:])  # type: ignore[arg-type]
    assert [item["scenario_code"] for item in lookups] == ["234569261000", ""]


@pytest.mark.parametrize(
    ("industry", "scenario", "expected"),
    [
        # 六级名称对上，或按一级行业对上通用场景：码表已有，带编码
        (CAR, ("车路云", "车路协同", "5G 全息路况出行服务"), ("exists", 0, "234569261000")),
        (TRAFFIC, ("视联网", "千里眼", ""), ("exists", 0, "221549000000")),
        # 第一个查不到的那一级就是新的那一级；后面的级别跟着它一起新
        (TRAFFIC, ("中医药数智化", "中医药国际交流合作平台", ""), ("new", 1, "")),
        (TRAFFIC, ("车路云", "绿色算力中心协同", "算电算水协同调度"), ("new", 2, "")),
        (TRAFFIC, ("车路云", "车路协同", "隧道智能巡检"), ("new", 3, "")),
        # 各级场景都有，只是没挂在这个行业下：新关联，不新增编号
        (CAR, ("物联网", "", ""), ("association", 0, "")),
        (("医卫行业", "卫生", "卫生"), ("车路云", "", ""), ("bad_industry", 0, "")),
        (TRAFFIC, ("", "", ""), ("invalid", 0, "")),
        (TRAFFIC, ("车路云", "", "某三级"), ("invalid", 0, "")),
    ],
)
def test_classify_tells_which_level_is_new(
    industry: tuple[str, str, str], scenario: tuple[str, str, str], expected: tuple[str, int, str]
) -> None:
    found = CodeBook.from_rows(ROWS).classify(ScenarioItem(industry, scenario))
    assert (found.kind, found.new_level, found.codes.scenario_code if found.codes else "") == expected


async def test_lookup_reports_the_classification_with_the_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rows(_session: Any) -> list[Any]:
        return ROWS

    monkeypatch.setattr(scenario_sync.repo, "scenario_codes", rows)
    names = ("industry_l1", "industry_l2", "industry_l3", "scenario_l1_name", "scenario_l2_name", "scenario_l3_name")
    items = [
        {"key": "a", **dict(zip(names, (*TRAFFIC, "车路云", "车路协同", "隧道智能巡检"), strict=True))},
        {"key": "b", **dict(zip(names, (*CAR, "物联网", "", ""), strict=True))},
    ]
    found = await scenario_sync.lookup(None, items)  # type: ignore[arg-type]  # 只用到打桩的仓储
    assert [(item["key"], item["kind"], item["new_level"], item["scenario_code"]) for item in found] == [
        ("a", "new", 3, ""),
        ("b", "association", 0, ""),
    ]


async def test_rename_changes_every_row_of_the_scenario_and_keeps_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from platform_common.errors import ApiError

    rows = [
        SimpleNamespace(
            scenario_l1_name="车路云",
            scenario_l2_name="车路协同",
            scenario_tag="车路协同",
            version=1,
            refresh_hash=lambda: None,
            scenario_code="234569000000",
        )
        for _ in range(2)
    ]
    events: list[dict[str, Any]] = []
    taken: set[tuple[str, ...]] = set()

    async def with_path(_session: Any, path: tuple[str, ...], *, lock: bool) -> list[Any]:
        return rows if path == ("车路云", "车路协同") else []

    async def exists(_session: Any, path: tuple[str, ...]) -> bool:
        return path in taken

    async def nothing(_session: Any) -> None:
        return None

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(scenario_sync.repo, "rows_with_path", with_path)
    monkeypatch.setattr(scenario_sync.repo, "path_exists", exists)
    monkeypatch.setattr(scenario_sync.repo, "lock_scenario_codes", nothing)
    monkeypatch.setattr(scenario_sync, "enqueue_event", record)
    actor = Actor(id="u1", name="张三")
    preview = await scenario_sync.rename(_Session(), actor, ["车路云", "车路协同"], "车路云协同", dry_run=True)  # type: ignore[arg-type]
    assert preview == {"rows": 2} and rows[0].scenario_l2_name == "车路协同"
    taken.add(("车路云", "车路云协同"))
    with pytest.raises(ApiError, match="已经有"):
        await scenario_sync.rename(_Session(), actor, ["车路云", "车路协同"], "车路云协同", dry_run=False)  # type: ignore[arg-type]
    taken.clear()
    done = await scenario_sync.rename(_Session(), actor, ["车路云", "车路协同"], "车路云协同", dry_run=False)  # type: ignore[arg-type]
    assert done == {"rows": 2}
    assert [(row.scenario_l2_name, row.scenario_tag, row.scenario_code, row.version) for row in rows] == [
        ("车路云协同", "车路云协同", "234569000000", 2)
    ] * 2
    assert events[0]["event_type"] == "codebook.scenario.renamed"
