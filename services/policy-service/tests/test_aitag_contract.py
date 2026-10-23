"""模板放进打标任务前的检查，以及从数据库取的测试数据和正式打标的输入一致。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.errors import ApiError, DependencyUnavailableError, NotFoundError

from app.aitag.application import samples
from app.aitag.domain.contract import COLUMNS, check_template


def test_template_checks_split_must_fix_from_worth_knowing() -> None:
    ok = check_template("type", ["政策标题", "政策正文", "上传码表"], ["政策类型名称"], system_code=True)
    assert ok == {"errors": [], "warnings": []}
    bad = check_template("interpret", ["企业名称", "政策正文"], ["政策概览"], system_code=False)
    assert bad["errors"][0].startswith("用了这个任务不提供的列：@【企业名称】")
    assert bad["errors"][1] == "输出字段缺少：一级行业、一级场景，结果写不回表"
    chance = check_template("opportunity", ["政策标题", "上传码表"], ["市场机会"], system_code=False)
    assert chance["errors"] == [] and len(chance["warnings"]) == 3  # 没用正文、没用行业场景、上传码表
    # 行业场景只有市场机会这一步才有。
    assert check_template("type", ["政策正文", "行业场景"], ["政策类型名称"], True)["errors"]
    assert "行业场景" in COLUMNS["opportunity"] and "源ID" in COLUMNS["type"]


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    async def task(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(content_max_chars=0)

    monkeypatch.setattr(samples.repo, "task", task)


async def test_type_samples_are_the_rows_the_type_task_would_send(
    monkeypatch: pytest.MonkeyPatch, config: None
) -> None:
    day = date(2026, 10, 18)
    source_row = {"content_id": "c1", "name": "航道通告", "prov_name": "广东省", "introduced_date": "2026-10-18"}
    monkeypatch.setattr(samples.source, "read_batch", lambda *args: [source_row] if args[0] == day else [])
    monkeypatch.setattr(
        samples.source, "read_contents", lambda ids: {"c1": "<html><body><p>正文一段</p></body></html>"}
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
        await samples.samples(None, "type", day, 99)  # type: ignore[arg-type]


async def test_opportunity_samples_carry_the_interpreted_scenes(monkeypatch: pytest.MonkeyPatch, config: None) -> None:
    tag = SimpleNamespace(
        source_content_id="c9", policy_name="数字政府方案", province_name="北京市", city_name="", issued_at="",
        issuing_dept="", policy_level="",
    )  # fmt: skip

    async def recent(*_: Any, interpreted: bool, limit: int) -> list[Any]:
        return [tag] if interpreted else []

    async def interpretations(*_: Any) -> dict[str, list[Any]]:
        return {"c9": [SimpleNamespace(industry_l1="党政行业", scenario_l1_name="数字政府")] * 2}

    monkeypatch.setattr(samples.repo, "recent_tags", recent)
    monkeypatch.setattr(samples.repo, "ai_interpretations", interpretations)
    monkeypatch.setattr(samples.source, "read_contents", lambda ids: {"c9": "正文"})
    out = await samples.samples(None, "opportunity", None, 5)  # type: ignore[arg-type]
    row = dict(zip(out["headers"], out["rows"][0], strict=True))
    assert row["行业场景"] == "党政行业/数字政府" and row["政策正文"] == "正文"
    with pytest.raises(NotFoundError, match="还没有被判为「需要解读」的政策"):
        await samples.samples(None, "interpret", None, 5)  # type: ignore[arg-type]
    assert [task["code"] for task in samples.contract()["tasks"]] == ["type", "interpret", "opportunity"]


async def test_source_outage_says_what_to_do(monkeypatch: pytest.MonkeyPatch, config: None) -> None:
    def down(*_: Any) -> Any:
        raise RuntimeError("mysql://user:secret@host refused")

    monkeypatch.setattr(samples.source, "read_batch", down)
    with pytest.raises(DependencyUnavailableError, match="源库暂时连不上") as caught:
        await samples.samples(None, "type", date(2026, 10, 18), 10)  # type: ignore[arg-type]
    assert "secret" not in str(caught.value)
