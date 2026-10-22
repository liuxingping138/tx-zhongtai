"""政策 AI 打标三个任务各跑一批的完整流程，在 P6 的 scheduler_test 库跑。源库和 ai-service、codebook-service 用替身。"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from app.aitag.application import pipeline, settings, tagging
from app.aitag.domain.models import PolicyAiRun, PolicyAiTask
from app.common import internal_clients
from app.common.errors import UserFacingError
from app.core.database import SessionLocal, engine
from app.policy.domain.models import BaseTag, Interpretation

pytestmark = pytest.mark.skipif(os.environ.get("SCHEDULER_INTEGRATION") != "1", reason="需要独立 scheduler_test 数据库")
PROMPT = "p" * 32
DAY = date(2026, 10, 1)


def _source(content_id: str, day: date, name: str) -> dict[str, Any]:
    return {
        "content_id": content_id,
        "name": name,
        "introduced_department": "某市数据局",
        "department_industry": "党政",
        "level": "地市级",
        "prov_id": "11",
        "prov_name": "北京市",
        "city_id": "1101",
        "city_name": "北京市",
        "introduced_date": "2026-09-30",
        "original_link": f"https://example.gov.cn/{content_id}",
        "collect_date": day,
    }


ROWS = [
    _source("c1", DAY, "数字政府建设方案"),
    _source("c2", DAY, "稳岗补贴通知"),
    _source("c3", DAY + timedelta(1), "智慧城市规划"),
]


class FakeAi:
    """记录发起的请求，按预设返回每行的回答。"""

    def __init__(self, answers: dict[str, str | None], *, cost: str = "0.5") -> None:
        self.answers = answers
        self.cost = cost
        self.created: list[dict[str, Any]] = []

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        if method == "POST" and path == "/internal/v1/pipeline-runs":
            self.created.append(kwargs["json"])
            return {"id": "r" * 32}
        if path.endswith("/results"):
            items = []
            for row in self.created[-1]["rows"]:
                answer = self.answers.get(row["源ID"])
                if answer is None:
                    items.append({"source_id": row["源ID"], "items": [], "error": "未执行（任务停止或中断）"})
                else:
                    items.append({"source_id": row["源ID"], "items": [{"政策类型名称": answer}], "error": ""})
            return {"items": items}
        return {"status": "done", "inference_cost": self.cost, "search_cost": "0", "error_message": ""}


@pytest_asyncio.fixture(autouse=True)
async def isolated(monkeypatch: pytest.MonkeyPatch):
    assert engine.url.database == "scheduler_test", "拒绝在业务数据库执行破坏性测试"
    async with SessionLocal() as session:
        await session.execute(delete(Interpretation))
        await session.execute(delete(BaseTag))
        await session.execute(delete(PolicyAiRun))
        await session.execute(
            text(
                "UPDATE policy_ai_tasks SET prompt_id=CASE WHEN code='type' THEN :prompt ELSE '' END,"
                " batch_size=3, daily_cost_limit=100, version=1,"
                " cursor_date=CASE WHEN code='type' THEN CAST(:day AS date) END, cursor_content_id=''"
            ),
            {"prompt": PROMPT, "day": DAY},
        )
        await session.commit()

    async def names(*_: Any, **__: Any) -> dict[str, str]:
        return {"text": "政策类型名称\t政策类型定义\t优先级\n信息化建设类\t\tP0\n资金扶持类\t\tP2"}

    monkeypatch.setattr(internal_clients, "codebook", names)
    monkeypatch.setattr(tagging.source, "read_contents", lambda ids: {cid: f"{cid} 的正文" for cid in ids})
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    monkeypatch.setattr(tagging, "today", lambda: DAY + timedelta(days=5))
    yield
    await engine.dispose()


def _serve(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], ai: FakeAi) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def read_batch(*args: Any) -> list[dict[str, Any]]:
        calls.append(args)
        return rows

    monkeypatch.setattr(tagging.source, "read_batch", read_batch)
    monkeypatch.setattr(internal_clients, "ai", ai)
    return calls


async def _state() -> tuple[PolicyAiTask, dict[str, BaseTag], list[PolicyAiRun]]:
    async with SessionLocal() as session:
        config = await session.get(PolicyAiTask, "type")
        tags = {str(row.source_content_id): row for row in await session.scalars(select(BaseTag))}
        runs = list(await session.scalars(select(PolicyAiRun)))
        assert config is not None
        return config, tags, runs


async def test_a_batch_tags_base_tags_and_moves_the_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    ai = FakeAi({"c1": "信息化建设、资金扶持类", "c2": "资金扶持类", "c3": "数字经济"})
    calls = _serve(monkeypatch, ROWS, ai)
    await tagging.run_batch(uuid.uuid4(), "type")
    config, tags, runs = await _state()
    assert calls[0][:3] == (DAY, "", 3)
    sent = ai.created[0]
    assert (sent["prompt_id"], sent["cost_limit"], sent["rows"][0]["政策正文"]) == (PROMPT, "100.00", "c1 的正文")
    assert (tags["c1"].policy_types, tags["c1"].need_interpret) == ("信息化建设类、资金扶持类", "是")
    assert (tags["c2"].need_interpret, tags["c3"].remark) == ("否", "AI 返回的类型不在码表里：数字经济")
    assert (config.cursor_date, config.cursor_content_id) == (DAY + timedelta(1), "c3")
    run = runs[0]
    assert (run.status, run.tagged_rows, run.type_failed, run.cost) == ("success", 3, 1, Decimal("0.5"))


async def test_retagging_updates_ai_rows_but_keeps_manual_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, ROWS, FakeAi({"c1": "资金扶持类", "c2": "资金扶持类", "c3": "资金扶持类"}))
    await tagging.run_batch(uuid.uuid4(), "type")
    async with SessionLocal() as session:
        edited = (await session.scalars(select(BaseTag).where(BaseTag.source_content_id == "c2"))).one()
        edited.remark, edited.updated_at = "人工核对过", edited.updated_at + timedelta(minutes=1)
        await session.commit()
    _serve(monkeypatch, ROWS, FakeAi({"c1": "信息化建设类", "c2": "信息化建设类", "c3": "信息化建设类"}))
    await tagging.run_batch(uuid.uuid4(), "type")
    _, tags, _ = await _state()
    assert tags["c1"].policy_types == "信息化建设类" and tags["c1"].version == 2
    assert (tags["c2"].policy_types, tags["c2"].remark) == ("资金扶持类", "人工核对过")


async def test_rows_not_run_before_the_cost_limit_are_read_again_next_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, ROWS, FakeAi({"c1": "资金扶持类", "c2": None, "c3": "资金扶持类"}))
    await tagging.run_batch(uuid.uuid4(), "type")
    config, tags, runs = await _state()
    # c3 虽然答了，但排在没执行的 c2 后面：进度只到 c1，下批从 c2 重读，c3 再打一次也只是更新。
    assert set(tags) == {"c1"} and (config.cursor_date, config.cursor_content_id) == (DAY, "c1")
    assert "剩余 2 条下批接着打" in runs[0].note


async def test_nothing_is_read_once_today_s_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _serve(monkeypatch, ROWS, FakeAi({}))
    async with SessionLocal() as session:
        await session.execute(text("UPDATE policy_ai_tasks SET daily_cost_limit=1"))
        session.add(
            PolicyAiRun(
                id=uuid.uuid4(),
                task="type",
                status="success",
                stage="done",
                cost=Decimal(2),
                type_cost=Decimal(2),
                started_at=tagging.utcnow(),
            )
        )
        await session.commit()
    monkeypatch.setattr(tagging, "today", pipeline.today)
    await tagging.run_batch(uuid.uuid4(), "type")
    _, tags, runs = await _state()
    assert calls == [] and tags == {}
    assert any("达到每日上限" in run.note for run in runs)


async def test_each_task_has_its_own_daily_budget_and_old_combined_runs_split_by_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SessionLocal() as session:
        # 拆分前的批次三步一起跑，记在类型判断名下，各步费用在各自的列里。
        session.add(
            PolicyAiRun(
                id=uuid.uuid4(),
                task="type",
                status="success",
                stage="done",
                source_rows=10,
                interpret_rows=24,
                cost=Decimal("0.6"),
                type_cost=Decimal("0.3"),
                interpret_cost=Decimal("0.2"),
                opportunity_cost=Decimal("0.1"),
                started_at=tagging.utcnow(),
            )
        )
        await session.commit()
        listed = {item["code"]: item for item in (await settings.list_tasks(session))["items"]}
    assert list(listed) == ["type", "interpret", "opportunity"]
    assert [listed[code]["spent_today"] for code in listed] == ["0.300000", "0.200000", "0.100000"]
    assert listed["type"]["cursor_date"] == DAY.isoformat() and listed["interpret"]["cursor_date"] == ""


async def test_a_task_without_a_template_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, ROWS, FakeAi({}))
    with pytest.raises(UserFacingError, match="政策解读"):
        await tagging.run_batch(uuid.uuid4(), "interpret")
    _, _, runs = await _state()
    assert [(run.task, run.status) for run in runs] == [("interpret", "failed")]


class StagedAi:
    """按步骤（看 caller_name）给每行回答：answers[步骤][源ID] = (输出条目, 错误)。"""

    def __init__(self, answers: dict[str, dict[str, tuple[list[dict[str, str]], str]]]) -> None:
        self.answers = answers
        self.created: list[dict[str, Any]] = []

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        if method == "POST" and path == "/internal/v1/pipeline-runs":
            self.created.append(kwargs["json"])
            return {"id": f"{len(self.created):032d}"}
        if path.endswith("/results"):
            body = self.created[int(path.split("/")[-2]) - 1]
            stage = next(name for name in self.answers if name in body["caller_name"])
            items = []
            for row in body["rows"]:
                found, error = self.answers[stage].get(row["源ID"], ([], "未执行（任务停止或中断）"))
                items.append({"source_id": row["源ID"], "items": found, "error": error})
            return {"items": items}
        return {"status": "done", "inference_cost": "0.1", "search_cost": "0", "error_message": ""}


def _interpretation(scene_l2: str, *, new: str, opportunity_type: str = "TO_G") -> dict[str, str]:
    return {
        "政策概览": f"{scene_l2}要文",
        "一级行业": "党政行业",
        "二级行业": "政务",
        "一级场景": "数字政府",
        "二级场景": scene_l2,
        "机会类型": opportunity_type,
        "是否新增场景": new,
        "适配产品": "移动云",
    }


@pytest.fixture
def staged(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    async def codebook(method: str, path: str, **kwargs: Any) -> Any:
        if path.endswith("/code-tables/policy_types"):
            return {"text": "政策类型名称\n信息化建设类\n资金扶持类"}
        # 只有「数字政府/一网统管」在码表里。
        return [
            {**item, "industry_code": "01", "scenario_code": "02", "industry_scenario_code": "0102"}
            if item["scenario_l2_name"] == "一网统管"
            else {**item, "industry_code": "", "scenario_code": "", "industry_scenario_code": ""}
            for item in kwargs["json"]["items"]
        ]

    monkeypatch.setattr(internal_clients, "codebook", codebook)

    async def enable() -> None:
        async with SessionLocal() as session:
            await session.execute(
                text("UPDATE policy_ai_tasks SET prompt_id=:p WHERE code IN ('interpret', 'opportunity')"),
                {"p": "i" * 32},
            )
            await session.execute(delete(Interpretation))
            await session.commit()

    return [enable]


async def _interpretations() -> dict[str, list[Interpretation]]:
    async with SessionLocal() as session:
        grouped: dict[str, list[Interpretation]] = {}
        for row in await session.scalars(select(Interpretation).order_by(Interpretation.scenario_l2_name)):
            grouped.setdefault(str(row.source_content_id), []).append(row)
        return grouped


async def test_the_pipeline_interprets_informatization_policies_and_fills_opportunities(
    monkeypatch: pytest.MonkeyPatch, staged: list[Any]
) -> None:
    await staged[0]()
    ai = StagedAi(
        {
            "类型判断": {
                "c1": ([{"政策类型名称": "信息化建设类"}], ""),
                "c2": ([{"政策类型名称": "资金扶持类"}], ""),
                "c3": ([{"政策类型名称": "信息化建设类"}], ""),
            },
            "政策解读": {
                "c1": ([_interpretation("一网统管", new="否"), _interpretation("城市大脑", new="是")], ""),
                "c3": ([], "限流"),
            },
            "市场机会": {"c1": ([{"行业": "党政行业", "场景": "数字政府", "市场机会": "机会A"}], "")},
        }
    )
    _serve(monkeypatch, ROWS, ai)
    for task in ("type", "interpret", "opportunity"):
        await tagging.run_batch(uuid.uuid4(), task)
    # 三个任务各跑一批。只有信息化建设类（c1、c3）进解读；c3 解读失败不进市场机会。
    assert [body["caller_name"][-4:] for body in ai.created] == ["类型判断", "政策解读", "市场机会"]
    assert [row["源ID"] for row in ai.created[1]["rows"]] == ["c1", "c3"]
    assert [row["源ID"] for row in ai.created[2]["rows"]] == ["c1"]
    assert "党政行业/数字政府" in ai.created[2]["rows"][0]["行业场景"]
    rows = (await _interpretations())["c1"]
    assert [(row.scenario_l2_name, row.industry_scenario_code, row.is_new_scenario) for row in rows] == [
        ("一网统管", "0102", "否"),
        ("城市大脑", "", "是"),
    ]
    assert {row.market_opportunity for row in rows} == {"机会A"}
    assert (rows[0].policy_summary, rows[0].adapted_products, rows[0].data_status) == (
        "一网统管要文",
        "移动云",
        "待验证",
    )
    _, tags, runs = await _state()
    assert tags["c1"].interpreted_at and tags["c1"].opportunity_at
    assert tags["c3"].interpreted_at and "AI 解读失败：限流" in tags["c3"].remark
    assert tags["c2"].interpreted_at is None
    by_task = {run.task: run for run in runs}
    assert (by_task["interpret"].source_rows, by_task["interpret"].interpret_rows) == (2, 2)
    assert by_task["interpret"].interpret_failed == 1
    assert (by_task["opportunity"].opportunity_rows, by_task["opportunity"].opportunity_failed) == (2, 0)
    assert by_task["type"].interpret_cost == 0 and by_task["interpret"].type_cost == 0


async def test_reinterpreting_keeps_rows_people_already_verified(
    monkeypatch: pytest.MonkeyPatch, staged: list[Any]
) -> None:
    await staged[0]()
    first = {
        "类型判断": {"c1": ([{"政策类型名称": "信息化建设类"}], "")},
        "政策解读": {"c1": ([_interpretation("一网统管", new="否"), _interpretation("城市大脑", new="是")], "")},
        "市场机会": {},
    }
    _serve(monkeypatch, ROWS[:1], StagedAi(first))
    await tagging.run_batch(uuid.uuid4(), "type")
    await tagging.run_batch(uuid.uuid4(), "interpret")
    async with SessionLocal() as session:
        verified = (
            await session.scalars(select(Interpretation).where(Interpretation.scenario_l2_name == "城市大脑"))
        ).one()
        verified.data_status = "人工验证"
        await session.execute(text("UPDATE policy_base_tags SET interpreted_at = NULL, opportunity_at = NULL"))
        await session.execute(
            text("UPDATE policy_ai_tasks SET cursor_date=:day, cursor_content_id='' WHERE code='type'"), {"day": DAY}
        )
        await session.commit()
    second = {
        "类型判断": {"c1": ([{"政策类型名称": "信息化建设类"}], "")},
        "政策解读": {"c1": ([_interpretation("一网通办", new="是"), _interpretation("城市大脑", new="是")], "")},
        "市场机会": {},
    }
    _serve(monkeypatch, ROWS[:1], StagedAi(second))
    await tagging.run_batch(uuid.uuid4(), "type")
    await tagging.run_batch(uuid.uuid4(), "interpret")
    rows = (await _interpretations())["c1"]
    # 一网统管（没人动过）被新答案替换；城市大脑已人工验证，保留原行、不重复建。
    assert [(row.scenario_l2_name, row.data_status) for row in rows] == [
        ("一网通办", "待验证"),
        ("城市大脑", "人工验证"),
    ]
