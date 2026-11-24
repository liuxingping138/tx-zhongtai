"""模板放进打标任务前的检查，以及从数据库取的测试数据和正式打标的输入一致。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.errors import ApiError, DependencyUnavailableError, NotFoundError

from app.aitag.application import samples
from app.aitag.domain.contract import COLUMNS, check_template
from app.aitag.domain.interpret_rules import ANSWER_FIELDS


def test_template_checks_split_must_fix_from_worth_knowing() -> None:
    ok = check_template("type", ["政策标题", "政策正文", "上传码表"], ["政策类型名称"], system_code=True)
    assert ok == {"errors": [], "warnings": []}
    bad = check_template("interpret", ["企业名称", "政策正文"], ["政策概览"], system_code=False)
    assert bad["errors"][0].startswith("用了这个任务不提供的列：@【企业名称】")
    assert bad["errors"][1] == "输出字段缺少：一级行业、一级场景，结果写不回表"
    chance = check_template("opportunity", ["政策标题", "上传码表"], ["市场机会"], system_code=False)
    # 没用正文、没用一级行业/一级场景、上传码表
    assert chance["errors"] == [] and len(chance["warnings"]) == 3
    # 模式 A：引用「一级行业」「一级场景」「政策正文」，只输出「市场机会」也完全合格，无提醒。
    mode_a = check_template("opportunity", ["一级行业", "一级场景", "政策正文"], ["市场机会"], True)
    assert mode_a == {"errors": [], "warnings": []}
    # 兼容旧写法：引用「行业场景」同样认可。
    named = check_template("opportunity", ["政策正文", "行业场景"], ["一级行业", "一级场景", "市场机会"], True)
    assert named == {"errors": [], "warnings": []}
    # 一级行业、一级场景、行业场景只有市场机会这一步才有。
    assert check_template("type", ["政策正文", "一级行业"], ["政策类型名称"], True)["errors"]
    assert {"一级行业", "一级场景", "行业场景"} <= set(COLUMNS["opportunity"]) and "源ID" in COLUMNS["type"]


def test_interpret_template_with_only_the_required_fields_warns_which_columns_stay_empty() -> None:
    """只输出一级行业、一级场景也能写回，但别让人以为能顶替正在用的解读模板。"""

    thin = check_template("interpret", ["政策正文"], ["一级行业", "一级场景", "判断理由"], system_code=True)
    assert thin["errors"] == []
    assert thin["warnings"] == ["没有输出政策要文、二级行业、三级行业、二级场景等 15 个字段，写回时这些列会空着"]
    full = [*ANSWER_FIELDS]
    assert check_template("interpret", ["政策正文"], full, system_code=True) == {"errors": [], "warnings": []}
    # 同一列的另一种写法也算输出了：「政策概览」就是「政策要文」。
    almost = [name for name in full if name not in ("政策要文", "备注")]
    assert check_template("interpret", ["政策正文"], almost, True)["warnings"] == ["没有输出备注，写回时这些列会空着"]


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    async def task(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(content_max_chars=0)

    async def no_timeout(*_: Any) -> None:
        return None

    monkeypatch.setattr(samples.repo, "task", task)
    monkeypatch.setattr(samples.repo, "limit_sample_queries", no_timeout)


async def test_type_samples_are_the_rows_the_type_task_would_send(
    monkeypatch: pytest.MonkeyPatch, config: None
) -> None:
    day = date(2026, 10, 18)
    source_row = {"content_id": "c1", "name": "航道通告", "prov_name": "广东省", "introduced_date": "2026-10-18"}
    page = "<html><body><p>正文一段</p></body></html>"
    # 页面上取测试数据：一次连接读这天的政策和正文，超时短、不重试（source.read_day_for_page）。
    monkeypatch.setattr(
        samples.source, "read_day_for_page", lambda *args: ([source_row], {"c1": page}) if args[0] == day else ([], {})
    )
    out = await samples.samples(None, "type", day, 10)  # type: ignore[arg-type]
    assert out["headers"] == list(COLUMNS["type"])
    row = dict(zip(out["headers"], out["rows"][0], strict=True))
    assert (row["源ID"], row["政策标题"], row["政策正文"], row["地市"]) == ("c1", "航道通告", "正文一段", "")
    assert out["file_name"] == "数据库样本-政策类型判断-1条.xlsx" and "2026-10-18 采集的源政策 1 条" in out["note"]
    with pytest.raises(NotFoundError, match="这天源库没有采集到政策"):
        await samples.samples(None, "type", date(2026, 1, 1), 10)  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="请选择采集日期"):
        await samples.samples(None, "type", None, 10)  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="条数要在"):
        await samples.samples(None, "type", day, 501)  # type: ignore[arg-type]


async def test_opportunity_samples_carry_the_interpreted_scenes(monkeypatch: pytest.MonkeyPatch, config: None) -> None:
    tag = SimpleNamespace(
        source_content_id="c9", policy_name="数字政府方案", province_name="北京市", city_name="", issued_at="",
        issuing_dept="", policy_level="",
    )  # fmt: skip

    async def recent(*_: Any, interpreted: bool, **__: Any) -> list[Any]:
        return [tag] if interpreted else []

    def row(industry: str, scene: str) -> Any:
        now = date(2026, 10, 18)
        return SimpleNamespace(
            industry_l1=industry, scenario_l1_name=scene, data_status="待验证", tagged_at=now, updated_at=now,
            source_content_id="c9",
        )  # fmt: skip

    async def interpretations(*_: Any) -> dict[str, list[Any]]:
        return {"c9": [row("党政行业", "数字政府"), row("党政行业", "数字政府"), row("教育行业", "智慧校园")]}

    monkeypatch.setattr(samples.repo, "recent_tags", recent)
    monkeypatch.setattr(samples.repo, "interpretations_by_source_ids", interpretations)
    monkeypatch.setattr(samples.source, "read_contents_for_page", lambda ids: {"c9": "正文"})
    out = await samples.samples(None, "opportunity", None, 5)  # type: ignore[arg-type]
    assert len(out["rows"]) == 2
    row0 = dict(zip(out["headers"], out["rows"][0], strict=True))
    row1 = dict(zip(out["headers"], out["rows"][1], strict=True))
    assert (row0["一级行业"], row0["一级场景"], row0["行业场景"], row0["政策正文"]) == (
        "党政行业",
        "数字政府",
        "党政行业/数字政府",
        "正文",
    )
    assert (row1["一级行业"], row1["一级场景"]) == ("教育行业", "智慧校园")
    with pytest.raises(NotFoundError, match="还没有被判为「需要解读」的政策"):
        await samples.samples(None, "interpret", None, 5)  # type: ignore[arg-type]

    async def configured(*_: Any) -> dict[str, Any]:
        return {"interpret": SimpleNamespace(prompt_id="p-interpret")}

    async def fake_l1() -> tuple[list[str], list[str]]:
        return ["党政行业", "教育行业"], ["数字政府"]

    monkeypatch.setattr(samples.repo, "tasks", configured)
    monkeypatch.setattr(samples.internal_clients, "scenario_l1_names", fake_l1)
    payload = await samples.contract(None)  # type: ignore[arg-type]
    tasks = payload["tasks"]
    assert "广东省" in payload["provinces"] and payload["industries"] == ["党政行业", "教育行业"]
    assert [task["code"] for task in tasks] == ["type", "interpret", "opportunity", "scenario", "enrich"]
    assert [task["prompt_id"] for task in tasks] == ["", "p-interpret", "", "", ""]
    assert ["二级行业"] in tasks[1]["optional_fields"] and tasks[0]["optional_fields"] == []


async def test_source_outage_says_what_to_do(monkeypatch: pytest.MonkeyPatch, config: None) -> None:
    def down(*_: Any) -> Any:
        raise RuntimeError("mysql://user:secret@host refused")

    monkeypatch.setattr(samples.source, "read_day_for_page", down)
    with pytest.raises(DependencyUnavailableError, match="源库暂时连不上") as caught:
        await samples.samples(None, "type", date(2026, 10, 18), 10)  # type: ignore[arg-type]
    assert "secret" not in str(caught.value)
