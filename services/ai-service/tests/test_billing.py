"""费用账单：试发、多轮对话怎么记账，按日期范围汇总的校验和输出。真实 SQL 汇总在集成测试里。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from platform_common.errors import ApiError

from app.application import billing
from app.application.model_configs import to_model
from tests.helpers import ACTOR, FakeSession, sample_models

FLASH, V32 = (to_model(row) for row in sample_models())


def test_tally_takes_tokens_from_usage_and_counts_searches_when_usage_has_none() -> None:
    tally = billing.CallTally()
    assert tally.empty
    for event in [
        {"text": "答"},
        {"tool_event": {"stage": "web_search_in_progress"}},
        {"tool_event": {"stage": "web_search_in_progress"}},
        {"usage": {"input_tokens": 1000, "output_tokens": 1000}},
    ]:
        tally.add(event)
    assert (tally.usage["input_tokens"], tally.search_events, tally.empty) == (1000, 2, False)


async def test_a_call_is_recorded_with_costs_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(billing, "SessionLocal", lambda: session)
    monkeypatch.setattr(billing, "utcnow", lambda: datetime(2026, 10, 22, 9, 0, tzinfo=UTC))
    tally = billing.CallTally()
    tally.add({"tool_event": {"stage": "web_search_in_progress"}})
    tally.add({"tool_event": {"stage": "web_search_in_progress"}})
    tally.add({"usage": {"input_tokens": 1000, "output_tokens": 1000}})
    await billing.record_call("chat", FLASH, tally, ACTOR)
    (row,) = session.added
    # 方舟 Flash 默认低优档：输入 0.0015、输出 0.0045 元/千 token；两次联网各 0.004 元。
    assert (row.kind, row.model_name, row.search_calls, row.created_by_name) == ("chat", FLASH.name, 2, "测试员")
    assert (row.inference_cost, row.search_cost) == (Decimal("0.006000"), Decimal("0.008000"))
    assert session.commits == 1


async def test_nothing_is_recorded_without_usage_and_failures_do_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(billing, "SessionLocal", lambda: session)
    await billing.record_call("trial", V32, billing.CallTally(), ACTOR)
    assert session.added == []

    def broken() -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(billing, "SessionLocal", broken)
    tally = billing.CallTally()
    tally.add({"usage": {"input_tokens": 1, "output_tokens": 1}})
    await billing.record_call("trial", V32, tally, ACTOR)  # 只写日志，不抛


async def test_daily_checks_the_range_and_formats_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[datetime, datetime]] = []

    async def daily(_session: Any, since: datetime, until: datetime) -> list[dict[str, Any]]:
        seen.append((since, until))
        return [
            {"day": date(2026, 10, 22), "model_id": "b", "model_name": "旧名",
             "scene": "测试", "category": "policy", "purpose": "试发", "calls": 2,
             "input_tokens": 10, "output_tokens": 5, "cost": Decimal("0.010000")},
            {"day": date(2026, 10, 22), "model_id": "b2", "model_name": "B",
             "scene": "测试", "category": "policy", "purpose": "试发", "calls": 1,
             "input_tokens": 1, "output_tokens": 1, "cost": Decimal("0.001000")},
            {"day": date(2026, 10, 21), "model_id": "gone", "model_name": "A",
             "scene": "日常调度", "category": "tender", "purpose": "批量提问", "calls": 1,
             "input_tokens": None, "output_tokens": None, "cost": None},
        ]  # fmt: skip

    monkeypatch.setattr(billing.repo, "daily", daily)

    async def names(_session: Any) -> dict[str, str]:
        return {"b": "B"}  # 改过名的模型用当前名字；配置里没有的 gone 用任务上记的名字

    monkeypatch.setattr(billing.repo, "model_names", names)
    data = await billing.daily(None, date(2026, 10, 21), date(2026, 10, 22))  # type: ignore[arg-type]
    # 北京时间 10-21 零点到 10-23 零点。
    assert seen == [(datetime(2026, 10, 20, 16, tzinfo=UTC), datetime(2026, 10, 22, 16, tzinfo=UTC))]
    assert [(item["day"], item["model"], item["cost"], item["input_tokens"]) for item in data["items"]] == [
        ("2026-10-21", "A", "0", 0),
        ("2026-10-22", "B", "0.011000", 11),
    ]
    # 模板类型编码换成页面上的中文名，业务分类原样带出，前端据此联动筛选。
    assert [(item["scene"], item["category"]) for item in data["items"]] == [("日常调度", "招投标"), ("测试", "政策")]
    with pytest.raises(ApiError, match="开始日期不能晚于结束日期"):
        await billing.daily(None, date(2026, 10, 22), date(2026, 10, 21))  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="最多查 366 天"):
        await billing.daily(None, date(2025, 1, 1), date(2026, 10, 21))  # type: ignore[arg-type]


async def test_trial_category_follows_the_template_or_the_chosen_type(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.application import asking
    from app.domain.categories import CategoryAccess

    async def require(_session: Any, _prompt_id: str) -> Any:
        return SimpleNamespace(category="customer")

    monkeypatch.setattr(asking, "require", require)
    tender_only = CategoryAccess(readable=frozenset({"tender"}), editable=frozenset({"tender"}))
    # 存过的模板以库里的类型为准；新模板取编辑页上选的，没有编辑权的类型不认，落到能编辑的第一个。
    assert await asking.trial_category(None, tender_only, "p1", "policy") == "customer"  # type: ignore[arg-type]
    assert await asking.trial_category(None, tender_only, None, "tender") == "tender"  # type: ignore[arg-type]
    assert await asking.trial_category(None, tender_only, None, "policy") == "tender"  # type: ignore[arg-type]
    assert await asking.trial_category(None, tender_only, None, None) == "tender"  # type: ignore[arg-type]
