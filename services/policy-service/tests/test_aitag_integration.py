"""政策 AI 打标一批的完整流程，在 P6 的 scheduler_test 库跑。源库和 ai-service、codebook-service 用替身。"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from app.aitag.application import tagging
from app.aitag.domain.models import PolicyAiConfig, PolicyAiRun
from app.common import internal_clients
from app.core.database import SessionLocal, engine
from app.policy.domain.models import BaseTag

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
        await session.execute(delete(BaseTag))
        await session.execute(delete(PolicyAiRun))
        await session.execute(
            text(
                "UPDATE policy_ai_config SET type_prompt_id=:prompt, batch_size=3, daily_cost_limit=100,"
                " cursor_date=:day, cursor_content_id='', version=1"
            ),
            {"prompt": PROMPT, "day": DAY},
        )
        await session.commit()

    async def names(*_: Any, **__: Any) -> dict[str, str]:
        return {"text": "政策类型名称\t政策类型定义\t优先级\n信息化建设类\t\tP0\n资金扶持类\t\tP2"}

    monkeypatch.setattr(internal_clients, "codebook", names)
    monkeypatch.setattr(tagging.source, "read_contents", lambda ids: {cid: f"{cid} 的正文" for cid in ids})
    monkeypatch.setattr(tagging, "POLL_SECONDS", 0)
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


async def _state() -> tuple[PolicyAiConfig, dict[str, BaseTag], list[PolicyAiRun]]:
    async with SessionLocal() as session:
        config = await session.get(PolicyAiConfig, 1)
        tags = {str(row.source_content_id): row for row in await session.scalars(select(BaseTag))}
        runs = list(await session.scalars(select(PolicyAiRun)))
        assert config is not None
        return config, tags, runs


async def test_a_batch_tags_base_tags_and_moves_the_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    ai = FakeAi({"c1": "信息化建设、资金扶持类", "c2": "资金扶持类", "c3": "数字经济"})
    calls = _serve(monkeypatch, ROWS, ai)
    await tagging.run_batch(uuid.uuid4())
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
    await tagging.run_batch(uuid.uuid4())
    async with SessionLocal() as session:
        edited = (await session.scalars(select(BaseTag).where(BaseTag.source_content_id == "c2"))).one()
        edited.remark, edited.updated_at = "人工核对过", edited.updated_at + timedelta(minutes=1)
        await session.commit()
    _serve(monkeypatch, ROWS, FakeAi({"c1": "信息化建设类", "c2": "信息化建设类", "c3": "信息化建设类"}))
    await tagging.run_batch(uuid.uuid4())
    _, tags, _ = await _state()
    assert tags["c1"].policy_types == "信息化建设类" and tags["c1"].version == 2
    assert (tags["c2"].policy_types, tags["c2"].remark) == ("资金扶持类", "人工核对过")


async def test_rows_not_run_before_the_cost_limit_are_read_again_next_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, ROWS, FakeAi({"c1": "资金扶持类", "c2": None, "c3": "资金扶持类"}))
    await tagging.run_batch(uuid.uuid4())
    config, tags, runs = await _state()
    # c3 虽然答了，但排在没执行的 c2 后面：进度只到 c1，下批从 c2 重读，c3 再打一次也只是更新。
    assert set(tags) == {"c1"} and (config.cursor_date, config.cursor_content_id) == (DAY, "c1")
    assert "剩余 2 条下次接着打" in runs[0].note


async def test_nothing_is_read_once_today_s_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _serve(monkeypatch, ROWS, FakeAi({}))
    async with SessionLocal() as session:
        await session.execute(text("UPDATE policy_ai_config SET daily_cost_limit=1"))
        session.add(
            PolicyAiRun(id=uuid.uuid4(), status="success", stage="done", cost=Decimal(2), started_at=tagging.utcnow())
        )
        await session.commit()
    monkeypatch.setattr(tagging, "today", lambda: tagging.utcnow().astimezone(tagging.BEIJING).date())
    await tagging.run_batch(uuid.uuid4())
    _, tags, runs = await _state()
    assert calls == [] and tags == {}
    assert any("达到每日上限" in run.note for run in runs)
