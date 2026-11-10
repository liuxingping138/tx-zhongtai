"""新增场景补描述：待补充的按场景路径合并交给 AI，写回改成待确认，人确认后改成已确认。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError

from app.application import scenario_enrich


def _row(industry: str, path: tuple[str, str, str], status: str) -> Any:
    return SimpleNamespace(
        industry_l1=industry,
        industry_l2="",
        industry_l3="",
        scenario_l1_name=path[0],
        scenario_l2_name=path[1],
        scenario_l3_name=path[2],
        scenario_l1_desc="",
        scenario_l2_desc="",
        scenario_l3_desc="",
        desc_90="",
        desc_130="",
        desc_pest="",
        scenario_tag="",
        scenario_level="",
        source_policy="某政策",
        enrich_status=status,
        version=1,
        updated_at=datetime(2026, 11, 2, tzinfo=UTC),
        refresh_hash=lambda: None,
    )


class _Session:
    async def flush(self) -> None:
        return None


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> list[Any]:  # 三行：两行同一个待补充场景，一行待确认
    rows = [
        _row("交通行业", ("智慧航空", "智慧机场工程建设管理", ""), "待补充"),
        _row("住建行业", ("智慧航空", "智慧机场工程建设管理", ""), "待补充"),
        _row("医卫行业", ("中医药数智化", "", ""), "待确认"),
    ]
    events: list[Any] = []

    async def with_enrich(_session: Any, status: str, *, lock: bool, path: tuple[str, ...] = ()) -> list[Any]:
        found = [r for r in rows if r.enrich_status == status]
        if path:
            found = [
                r
                for r in found
                if tuple(n for n in (r.scenario_l1_name, r.scenario_l2_name, r.scenario_l3_name) if n) == path
            ]
        return found

    async def nodes(_session: Any) -> list[Any]:
        return [
            (("交通行业", "", ""), ("智慧航空", "", ""), ("航空的描述", "", ""), ""),
            (("交通行业", "", ""), ("智慧航空", "智慧空侧", ""), ("", "空侧的描述", ""), ""),
        ]

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(scenario_enrich.repo, "rows_with_enrich", with_enrich)
    monkeypatch.setattr(scenario_enrich.repo, "scenario_nodes", nodes)
    monkeypatch.setattr(scenario_enrich, "enqueue_event", record)
    return rows


async def test_backlog_merges_rows_of_one_scenario_and_gives_references(store: list[Any]) -> None:
    items = await scenario_enrich.backlog(_Session(), 10)  # type: ignore[arg-type]
    assert [(i["key"], i["rows"], i["level"]) for i in items] == [("智慧航空 > 智慧机场工程建设管理", 2, 2)]
    assert items[0]["parent_desc"] == "航空的描述"
    assert items[0]["examples"] == [{"name": "智慧空侧", "desc": "空侧的描述"}]
    assert await scenario_enrich.count(_Session(), "待补充") == 1  # type: ignore[arg-type]


async def test_ai_text_goes_to_every_row_then_a_person_confirms(store: list[Any]) -> None:
    path = ["智慧航空", "智慧机场工程建设管理"]
    out = await scenario_enrich.write(
        _Session(), [{"path": path, "desc_90": "机场建设期数字化管理", "level_desc": "本级描述"}]
    )  # type: ignore[arg-type]
    first, second = store[0], store[1]
    assert out == {"updated": 2}
    assert (first.desc_90, first.scenario_l2_desc, first.enrich_status, first.scenario_tag, first.scenario_level) == (
        "机场建设期数字化管理",
        "本级描述",
        "待确认",
        "智慧机场工程建设管理",
        "2",
    )
    assert second.desc_90 == "机场建设期数字化管理" and first.updated_by_name == "政策AI打标"
    actor = Actor(id="u1", name="张三")
    done = await scenario_enrich.confirm(
        _Session(), actor, path, {"desc_90": "改过的描述", "desc_130": "", "desc_pest": "", "level_desc": "本级描述"}
    )  # type: ignore[arg-type]
    assert done == {"rows": 2} and (first.desc_90, first.enrich_status, first.updated_by_name) == (
        "改过的描述",
        "已确认",
        "张三",
    )
    with pytest.raises(ApiError, match="不在待确认"):
        await scenario_enrich.confirm(_Session(), actor, path, {})  # type: ignore[arg-type]


async def test_backlog_ignores_empty_or_gapped_scenario_names(
    store: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """三级场景全空或中间跳级时，不能拼出 scenario_l0_desc 崩掉整个列表，也不把三级名错当二级。"""

    store.extend([_row("交通行业", ("", "", ""), "待补充"), _row("交通行业", ("智慧政务", "", "一网通办"), "待补充")])
    items = await scenario_enrich.backlog(_Session(), 10)  # type: ignore[arg-type]
    assert [i["key"] for i in items] == ["智慧航空 > 智慧机场工程建设管理", "智慧政务"]
    assert scenario_enrich._level_desc(store[0], 0) == ""
