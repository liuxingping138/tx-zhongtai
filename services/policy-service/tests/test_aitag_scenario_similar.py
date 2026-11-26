"""新增场景找相似：交给模型的行、模型回答怎么写回候选、模板约定。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.aitag.application import scenario_similar
from app.aitag.application.pipeline import Spend
from app.aitag.domain.contract import check_template
from app.common import internal_clients
from app.policy.domain import candidates as domain

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def _candidate(name: str, **extra: Any) -> domain.ScenarioCandidate:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "kind": domain.KIND_NEW,
        "new_level": 2,
        "level_label": "二级",
        "scenario_l1": "智慧航空",
        "scenario_l2": name,
        "scenario_l3": "",
        "status": domain.STATUS_PENDING,
        "main_industry": "交通行业",
        "ai_verdict": "",
        "ai_similar": "",
        "ai_target": "",
        "ai_reason": "",
        "ai_checked_at": None,
        **extra,
    }
    return domain.ScenarioCandidate(**values)


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("同一个场景", domain.AI_SAME),
        ("是同一回事", domain.AI_SAME),
        ("新场景", domain.AI_NEW),
        ("太细，应归到已有场景下", domain.AI_UNDER),
    ],
)
def test_verdicts_fold_into_three_conclusions(text: str, verdict: str) -> None:
    assert domain.ai_verdict(text) == verdict


def test_paths_written_any_way_line_up_with_the_codebook() -> None:
    assert domain.ai_path("「智慧航空 › 智慧航站楼」") == "智慧航空 > 智慧航站楼"
    assert domain.ai_path("智慧航空/智慧航站楼/统一联动安防") == "智慧航空 > 智慧航站楼 > 统一联动安防"


def test_the_template_contract_for_finding_similar_scenarios() -> None:
    fine = check_template("scenario", ["新增场景", "同行业已有场景"], ["判断", "最像的已有场景", "理由"], True)
    assert fine == {"errors": [], "warnings": []}  # 没有政策正文这一列，不提醒没用正文
    bad = check_template("scenario", ["新增场景", "政策正文"], ["判断"], True)
    assert "政策正文" in bad["errors"][0] and "最像的已有场景" in bad["errors"][1]
    assert any("同行业已有场景" in warning for warning in bad["warnings"])


def test_only_a_scenario_found_in_the_codebook_becomes_the_merge_target() -> None:
    known = {"智慧航空 > 智慧航站楼"}
    same = _candidate("航站楼智能化")
    item = {"判断": "同一个场景", "最像的已有场景": "智慧航空 › 智慧航站楼", "理由": "说法不同"}
    assert scenario_similar._judge(same, {"items": [item]}, known)
    assert (same.ai_verdict, same.ai_target, same.ai_reason) == ("同一个场景", "智慧航空 > 智慧航站楼", "说法不同")
    made_up = _candidate("机场建设")
    scenario_similar._judge(made_up, {"items": [{"判断": "同一个场景", "最像的已有场景": "智慧机场"}]}, known)
    assert (made_up.ai_similar, made_up.ai_target) == ("智慧机场", "")  # 码表里没有，不预选
    new = _candidate("低空飞行服务保障")
    scenario_similar._judge(new, {"items": [{"判断": "新场景", "最像的已有场景": "智慧航空 > 智慧航站楼"}]}, known)
    assert (new.ai_verdict, new.ai_target) == ("新场景", "")
    failed = _candidate("x")
    assert not scenario_similar._judge(failed, {"error": "返回格式不对", "items": []}, known)
    assert (failed.ai_verdict, failed.ai_reason) == ("判断失败", "返回格式不对")


class Session:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


async def test_a_batch_asks_once_per_scenario_and_writes_back(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _candidate("航站楼智能化", policy_count=9), _candidate("低空飞行服务保障", policy_count=3)
    session = Session()
    sent: dict[str, Any] = {}

    async def backlog(_session: Any, limit: int) -> list[Any]:
        return [first, second][:limit]

    async def inputs(_session: Any, items: list[Any]) -> dict[str, Any]:
        return {str(item.id): {"industries": ["交通行业"], "reasons": ["码表无对应场景"]} for item in items}

    async def codebook(_method: str, _path: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {"key": item["key"], "industry_paths": ["智慧航空", "智慧航空 > 智慧航站楼"]}
            for item in kwargs["json"]["items"]
        ]

    async def ask(_run_id: Any, _spend: Any, **kwargs: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sent.update(kwargs)
        return {"status": "done"}, [
            {"items": [{"判断": "同一个场景", "最像的已有场景": "智慧航空 > 智慧航站楼", "理由": "说法不同"}]},
            {"error": "未执行（费用到上限）", "items": []},
        ]

    locked_batches: list[list[uuid.UUID]] = []

    async def locked_many(_session: Any, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
        locked_batches.append(list(candidate_ids))
        by_id = {first.id: first, second.id: second}
        return {cid: by_id[cid] for cid in candidate_ids if cid in by_id}

    async def nothing(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(scenario_similar.repo, "scenario_backlog", backlog)
    monkeypatch.setattr(scenario_similar.scenario_candidates, "ai_inputs", inputs)
    monkeypatch.setattr(scenario_similar.scenario_candidates, "locked_many", locked_many)
    monkeypatch.setattr(internal_clients, "codebook", codebook)
    monkeypatch.setattr(scenario_similar, "ask", ask)
    monkeypatch.setattr(scenario_similar, "SessionLocal", lambda: session)
    monkeypatch.setattr(scenario_similar, "update_run", nothing)
    monkeypatch.setattr(scenario_similar, "enqueue_event", nothing)

    config = SimpleNamespace(batch_size=10, prompt_id="p" * 32)
    note = await scenario_similar.similar_step(uuid.uuid4(), config, Spend(limit=Decimal(20), before=Decimal(0)))  # type: ignore[arg-type]
    rows = sent["rows"]
    assert all(row["源ID"] for row in rows)  # ai-service 要求每行都有，结果按它对回来
    assert [row["新增场景"] for row in rows] == ["智慧航空 > 航站楼智能化", "智慧航空 > 低空飞行服务保障"]
    assert rows[0]["同行业已有场景"] == "智慧航空\n智慧航空 > 智慧航站楼" and rows[0]["AI理由"] == "码表无对应场景"
    assert (first.ai_verdict, first.ai_target) == ("同一个场景", "智慧航空 > 智慧航站楼")
    assert first.ai_checked_at is not None and second.ai_checked_at is None  # 没轮到的下批再问
    assert locked_batches == [[first.id]]
    assert session.committed and "AI 判断了 1 个" in note and "1 个下批接着判断" in note


async def test_ai_inputs_uses_two_batched_breakdown_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.policy.application import scenario_candidates as sc_app

    first, second = _candidate("航站楼智能化"), _candidate("低空飞行服务保障")
    calls: list[Any] = []

    async def fake_breakdown_many(
        _session: Any, ids: list[uuid.UUID], column: Any, **_kwargs: Any
    ) -> dict[uuid.UUID, list[tuple[Any, int]]]:
        calls.append((list(ids), column.key))
        if column.key == "industry_l1":
            return {first.id: [("交通行业", 5)], second.id: [("航空行业", 2)]}
        return {first.id: [("说法更贴合", 4), ("AI 标为已有场景", 9)], second.id: []}

    monkeypatch.setattr(sc_app.repo, "breakdown_many", fake_breakdown_many)
    out = await sc_app.ai_inputs(Session(), [first, second])  # type: ignore[arg-type]
    assert len(calls) == 2
    assert calls[0][1] == "industry_l1" and calls[1][1] == "remark"
    assert out[str(first.id)] == {"industries": ["交通行业"], "reasons": ["说法更贴合"]}
    assert out[str(second.id)] == {"industries": ["航空行业"], "reasons": []}
