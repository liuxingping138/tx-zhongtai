"""新增场景补描述：交给模型的行、回答怎么写回码表、模板约定。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.aitag.application import scenario_describing
from app.aitag.application.pipeline import Spend
from app.aitag.domain.contract import check_template
from app.common import internal_clients

ITEM = {
    "key": "智慧航空 > 智慧机场工程建设管理",
    "path": ["智慧航空", "智慧机场工程建设管理"],
    "level": 2,
    "industries": ["交通行业/交通运输、仓储和邮政业/航空"],
    "source_policy": "蓝图变实景三晋崛起空港新地标",
    "parent_desc": "航空的描述",
    "examples": [{"name": "智慧空侧", "desc": "空侧的描述"}],
}


def test_rows_carry_references_for_writing_in_the_codebook_style() -> None:
    (row,) = scenario_describing.prompt_rows([ITEM])
    assert row["场景路径"] == "智慧航空 > 智慧机场工程建设管理" and row["新增级别"] == "二级"
    assert row["同级场景示例"] == "智慧空侧：空侧的描述" and row["上级场景描述"] == "航空的描述"
    assert (
        scenario_describing.prompt_rows([{**ITEM, "examples": [], "parent_desc": ""}])[0]["同级场景示例"] == "（没有）"
    )


def test_answers_skip_unasked_and_mark_failures_for_people_to_fill() -> None:
    other = {**ITEM, "path": ["中医药数智化"]}
    third = {**ITEM, "path": ["低空经济"]}
    results = [
        {"items": [{"场景描述90字": "机场建设期数字化管理", "本级场景描述": "本级"}]},
        {"error": "返回格式不对", "items": []},
        {"error": "未执行（费用到上限）", "items": []},
    ]
    written, done, failed = scenario_describing.answers([ITEM, other, third], results)
    assert (done, failed) == (1, 1)
    assert written[0] == {
        "path": ["智慧航空", "智慧机场工程建设管理"],
        "desc_90": "机场建设期数字化管理",
        "desc_130": "",
        "desc_pest": "",
        "level_desc": "本级",
    }
    assert written[1] == {"path": ["中医药数智化"]} and len(written) == 2  # 没轮到的下批再写


def test_the_template_contract_for_describing() -> None:
    assert check_template("enrich", ["场景路径", "同级场景示例"], ["场景描述90字"], True)["errors"] == []
    assert "场景描述90字" in check_template("enrich", ["场景路径"], ["本级场景描述"], True)["errors"][0]


async def test_a_batch_writes_back_to_the_codebook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    async def codebook(_method: str, path: str, **kwargs: Any) -> Any:
        calls.append((path, kwargs.get("json")))
        return [ITEM] if path.endswith("enrich-backlog") else {"updated": 2}

    async def ask(*_: Any, **kwargs: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return {"status": "done"}, [{"items": [{"场景描述90字": "描述"}]}]

    async def nothing(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(internal_clients, "codebook", codebook)
    monkeypatch.setattr(scenario_describing, "ask", ask)
    monkeypatch.setattr(scenario_describing, "update_run", nothing)
    config = SimpleNamespace(batch_size=200, prompt_id="p" * 32)
    note = await scenario_describing.describe_step(uuid.uuid4(), config, Spend(limit=Decimal(20), before=Decimal(0)))  # type: ignore[arg-type]
    assert calls[0] == ("/internal/v1/scenarios/enrich-backlog", {"limit": 200})
    assert calls[1][0] == "/internal/v1/scenarios/enrich" and calls[1][1]["items"][0]["desc_90"] == "描述"
    assert "AI 写好描述 1 个" in note
