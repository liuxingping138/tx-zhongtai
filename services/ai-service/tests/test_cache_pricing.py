"""上下文缓存：用量里取命中缓存的 token、按缓存价算钱，并一路记到任务、费用流水、试发用量和账单。"""

from __future__ import annotations

import csv
import importlib.util
from collections import deque
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from platform_common.errors import ApiError

from app.application import asking, batch_execute, billing, model_configs, row_asking
from app.application.batch_output import (
    LEGACY_RAW_COLUMNS,
    RAW_COLUMNS,
    RowResult,
    append_raw,
    copy_answers,
    iter_outcomes,
    raw_at,
    read_raw,
    start_raw,
)
from app.application.batch_runs import to_dict as run_to_dict
from app.application.run_costs import Ledger, Spend
from app.core import storage
from app.core.llm import extract_usage
from app.domain.llm_models import calc_costs
from app.domain.models import AiModel, BatchRun, CallUsage, RunCost
from tests.helpers import ACTOR, RUN_ID, FakeSession, ai_model, run

_BEIJING = timezone(timedelta(hours=8))
BUSY = datetime(2026, 10, 21, 10, 0, tzinfo=_BEIJING)  # 周三上午，高峰
IDLE = datetime(2026, 10, 21, 22, 0, tzinfo=_BEIJING)

# 方舟 V4.1-Flash 经济版：分时计价，缓存平时 0.000016、高峰 0.000032 元/千 token。
ECONOMY = model_configs.to_model(
    ai_model(
        service_tier="",
        input_price=Decimal("0.0008"),
        output_price=Decimal("0.0032"),
        flex_input_price=None,
        flex_output_price=None,
        peak_input_price=Decimal("0.0016"),
        peak_output_price=Decimal("0.0064"),
        peak_hours="09:00-12:00,14:00-18:00",
        cache_price=Decimal("0.000016"),
        peak_cache_price=Decimal("0.000032"),
    )
)
# 方舟 V4-Flash 正式版：默认低优档，缓存价不分档 0.0001。
FLASH = model_configs.to_model(ai_model(cache_price=Decimal("0.0001")))


@pytest.mark.parametrize(
    ("usage", "cached"),
    [
        ({"input_tokens": 100, "output_tokens": 1, "input_tokens_details": {"cached_tokens": 60}}, 60),
        ({"prompt_tokens": 100, "completion_tokens": 1, "prompt_tokens_details": {"cached_tokens": 30}}, 30),
        ({"input_tokens": 100, "output_tokens": 1, "cached_tokens": 20}, 20),
        # Responses 的写法优先；明细里没给的退到下一种。
        ({"input_tokens": 100, "input_tokens_details": {"cached_tokens": 5}, "cached_tokens": 9}, 5),
        ({"input_tokens": 100, "input_tokens_details": {}, "prompt_tokens_details": {"cached_tokens": 7}}, 7),
        # 没给、给错、越界都夹回 0 到输入数之间。
        ({"input_tokens": 100, "output_tokens": 1}, 0),
        ({"input_tokens": 100, "input_tokens_details": {"cached_tokens": "abc"}}, 0),
        ({"input_tokens": 100, "input_tokens_details": {"cached_tokens": -3}}, 0),
        ({"input_tokens": 100, "input_tokens_details": {"cached_tokens": 500}}, 100),
    ],
)
def test_cached_tokens_are_read_from_every_usage_shape(usage: dict[str, Any], cached: int) -> None:
    result = extract_usage({"usage": usage})
    assert result is not None and result["cached_tokens"] == cached


def test_cache_price_follows_peak_hours_and_ignores_tier() -> None:
    assert ECONOMY.cache_price_at(BUSY) == Decimal("0.000032")
    assert ECONOMY.cache_price_at(IDLE) == Decimal("0.000016")
    # 缓存价不分常规、低优档：低优档照样用配的缓存价。
    assert FLASH.service_tier == "flex" and FLASH.cache_price_at(BUSY) == Decimal("0.0001")
    # 没配缓存价按此刻的输入价，费用和没有缓存计价时一样。
    plain = replace(ECONOMY, cache_price=None, peak_cache_price=None)
    assert plain.cache_price_at(BUSY) == Decimal("0.0016")
    assert plain.cache_price_at(IDLE) == Decimal("0.0008")
    assert calc_costs(plain, 3000, 1000, 0, BUSY, 2000) == calc_costs(plain, 3000, 1000, 0, BUSY)
    # 只有高峰缓存价、没有平时缓存价（库里的旧数据）：平时段按输入价。
    only_peak = replace(ECONOMY, cache_price=None, peak_input_price=None, peak_output_price=None)
    assert only_peak.cache_price_at(IDLE) == Decimal("0.0008")
    assert only_peak.cache_price_at(BUSY) == Decimal("0.000032")
    # 只按缓存分时的也在价格旁写清时段。
    assert only_peak.price_note(IDLE).startswith("平时价")


def test_cached_tokens_are_billed_at_the_cache_price() -> None:
    # 高峰：1000 未命中 × 0.0016 + 2000 命中 × 0.000032 + 1000 输出 × 0.0064。
    inference, _ = calc_costs(ECONOMY, 3000, 1000, 0, BUSY, 2000)
    assert inference == Decimal("0.0016") + Decimal("0.000064") + Decimal("0.0064")
    inference, _ = calc_costs(ECONOMY, 3000, 1000, 0, IDLE, 2000)
    assert inference == Decimal("0.0008") + Decimal("0.000032") + Decimal("0.0032")
    # 低优档：未命中按低优输入价，命中按缓存价；联网照旧按次。
    inference, search = calc_costs(FLASH, 3000, 1000, 2, BUSY, 2000)
    assert (inference, search) == (Decimal("0.0015") + Decimal("0.0002") + Decimal("0.0045"), Decimal("0.008"))
    # 命中数越界（大于输入、为负）夹住，钱不会算成负的。
    assert calc_costs(ECONOMY, 1000, 0, 0, IDLE, 5000)[0] == Decimal("0.000016")
    assert calc_costs(ECONOMY, 1000, 0, 0, IDLE, -5)[0] == Decimal("0.000800")


_FORM = {
    "name": "经济版",
    "provider": "ark",
    "endpoint": "ep-economy",
    "input_price": "0.0008",
    "output_price": "0.0032",
}


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def record(_session: Any, **kwargs: Any) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(model_configs, "enqueue_event", record)
    return seen


async def test_model_config_saves_cache_prices(events: list[dict[str, Any]]) -> None:
    out = await model_configs.create_model(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        {**_FORM, "id": "m1", "cache_price": "0.000016", "peak_cache_price": "0.000032"},
    )
    assert (out["cache_price"], out["peak_cache_price"]) == ("0.000016", "0.000032")
    # 只配了高峰缓存价也要有高峰时段，没填就用默认时段。
    assert out["peak_hours"] == "09:00-12:00,14:00-18:00"
    assert events[0]["changes"]["cache_price"] == "0.000016"
    plain = await model_configs.create_model(FakeSession(), ACTOR, {**_FORM, "id": "m2"})  # type: ignore[arg-type]
    assert (plain["cache_price"], plain["peak_cache_price"], plain["peak_hours"]) == ("", "", "")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"peak_cache_price": "0.00003"}, "也要填平时的缓存单价"),
        ({"cache_price": "abc"}, "缓存单价要填数字"),
        ({"cache_price": "0.0000001"}, "6 位小数"),
    ],
)
async def test_model_config_rejects_bad_cache_prices(
    overrides: dict[str, Any], message: str, events: list[dict[str, Any]]
) -> None:
    with pytest.raises(ApiError, match=message):
        await model_configs.create_model(FakeSession(), ACTOR, {**_FORM, "id": "m1", **overrides})  # type: ignore[arg-type]
    assert events == []


def test_trial_page_gets_the_cache_price_of_this_moment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asking, "utcnow", lambda: BUSY)
    assert asking.model_info(ECONOMY)["cache_price"] == "0.000032"
    monkeypatch.setattr(asking, "utcnow", lambda: IDLE)
    assert asking.model_info(ECONOMY)["cache_price"] == "0.000016"


async def test_trial_call_records_cached_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(billing, "SessionLocal", lambda: session)
    monkeypatch.setattr(billing, "utcnow", lambda: IDLE)
    tally = billing.CallTally()
    tally.add({"usage": {"input_tokens": 3000, "output_tokens": 1000, "cached_tokens": 2000}})
    await billing.record_call("trial", ECONOMY, tally, ACTOR)
    (row,) = session.added
    assert isinstance(row, CallUsage) and row.cached_tokens == 2000
    assert row.inference_cost == Decimal("0.004032")


async def test_retries_add_up_cached_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(
        [
            RowResult("", "问", "", 100, 0, 0, "超时", 0.1, retryable=True, cached_tokens=80),
            RowResult("", "问", "答", 100, 10, 0, "", 0.1, cached_tokens=90),
        ]
    )

    async def once(*_args: Any) -> RowResult:
        return next(answers)

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(row_asking, "call_model_once", once)
    monkeypatch.setattr(row_asking.asyncio, "sleep", no_wait)
    result = await row_asking.ask_row(ECONOMY, "问", False, [], None)  # type: ignore[arg-type]
    assert (result.input_tokens, result.cached_tokens, result.attempts) == (200, 170, 2)


async def test_batch_row_cost_and_ledger_count_cached_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    job = batch_execute.Job(run=run(), model=ECONOMY, headers=[], rows=[{}], pending=deque())
    storage.run_dir(RUN_ID).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(batch_execute, "utcnow", lambda: IDLE)
    await batch_execute._record(job, RowResult("a1", "问", "答", 3000, 1000, 0, "", 0.1, cached_tokens=2000))
    assert job.cached_tokens == 2000
    assert job.inference_cost == Decimal("0.004032")
    assert batch_execute._progress(job)["cached_tokens"] == 2000
    (spend,) = job.ledger.take().values()
    assert (spend.cached_tokens, spend.inference_cost) == (2000, Decimal("0.004032"))


def test_spend_adds_cached_tokens_and_keeps_positional_fields() -> None:
    ledger = Ledger()
    ledger.add(IDLE, Spend(10, 1, 0, Decimal("0.1"), Decimal(0), cached_tokens=4))
    ledger.add(IDLE, Spend(20, 2, 1, Decimal("0.2"), Decimal("0.004"), cached_tokens=6))
    (spend,) = ledger.take().values()
    assert spend == Spend(30, 3, 1, Decimal("0.3"), Decimal("0.004"), cached_tokens=10)


def test_raw_file_carries_cached_tokens(tmp_path: Path) -> None:
    raw = tmp_path / "temp.csv"
    start_raw(raw)
    append_raw(raw, RowResult("a1", "问", "答", 300, 20, 0, "", 0.1, cached_tokens=200).raw_row("模型"))
    with raw.open(encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == RAW_COLUMNS and rows[1][-1] == "200"
    assert read_raw(raw)["a1"].cached_tokens == 200
    (outcome,) = list(iter_outcomes(raw) or [])
    found = raw_at(raw, outcome.offset)
    assert found is not None and found.cached_tokens == 200


def test_raw_file_started_before_the_cache_column_stays_readable(tmp_path: Path) -> None:
    """缓存列上线前开始的任务续跑：照旧文件的 8 列接着写，读回来缺的缓存列算 0，按位置取行也认得。"""

    raw = tmp_path / "temp.csv"
    with raw.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(LEGACY_RAW_COLUMNS)
    (tmp_path / "temp.outcomes.jsonl").write_text("", encoding="utf-8")
    start_raw(raw)  # 已有文件不重建
    append_raw(raw, RowResult("a1", "问", "答", 300, 20, 0, "", 0.1, cached_tokens=200).raw_row("模型"))
    with raw.open(encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == LEGACY_RAW_COLUMNS and len(rows[1]) == len(LEGACY_RAW_COLUMNS)
    result = read_raw(raw)["a1"]
    assert (result.input_tokens, result.cached_tokens) == (300, 0)
    (outcome,) = list(iter_outcomes(raw) or [])
    found = raw_at(raw, outcome.offset)
    assert found is not None and (found.text, found.cached_tokens) == ("答", 0)
    # 从旧文件抄答案到新任务：新文件是 9 列，缺的缓存列留空、读回来是 0。
    target = tmp_path / "new.csv"
    assert copy_answers(raw, target, {"a1": ["b1"]}, []) == 1
    copied = read_raw(target)["b1"]
    assert (copied.text, copied.cached_tokens) == ("答", 0)


def test_new_columns_have_chinese_comments_and_match_the_migration() -> None:
    for model in (BatchRun, RunCost, CallUsage):
        column = model.__table__.c["cached_tokens"]
        assert column.comment == "缓存命中token" and column.server_default is not None
    assert AiModel.__table__.c["cache_price"].comment == "缓存输入单价（元/千token）"
    assert AiModel.__table__.c["peak_cache_price"].comment == "高峰缓存单价（元/千token）"
    path = Path(__file__).parents[1] / "migrations" / "versions" / "d6f9b2c31616_cache_tokens.py"
    # 历史迁移不能 import 运行时模型：模型以后加列，空库从头迁移会失败。
    text = path.read_text(encoding="utf-8")
    assert "from app" not in text and "import app" not in text
    spec = importlib.util.spec_from_file_location("cache_tokens_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "c5e8a1b21515"
    assert {table for table, _ in module._TOKEN_TABLES} == {"ai_batch_runs", "ai_run_costs", "ai_call_usages"}
    # 已有方舟接入点补上的缓存价和方舟控制台一致。
    assert module._CACHE_PRICES == {
        "ep-20260915173105-gv9tb": ("0.0001", None),
        "ep-20261021162727-fcx55": ("0.000016", "0.000032"),
        "ep-20260915170840-m8pwt": ("0.0003", None),
    }


async def test_billing_rows_carry_cached_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    async def daily(_session: Any, _since: datetime, _until: datetime) -> list[dict[str, Any]]:
        row = {"day": date(2026, 10, 22), "model_id": "m", "model_name": "M", "scene": "测试", "category": "policy"}
        return [
            {**row, "purpose": "试发", "calls": 1, "input_tokens": 100, "output_tokens": 1, "cached_tokens": 60,
             "cost": Decimal("0.01")},
            {**row, "purpose": "试发", "calls": 1, "input_tokens": 50, "output_tokens": 1, "cached_tokens": 10,
             "cost": Decimal("0.01")},
        ]  # fmt: skip

    async def names(_session: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(billing.repo, "daily", daily)
    monkeypatch.setattr(billing.repo, "model_names", names)
    data = await billing.daily(None, date(2026, 10, 22), date(2026, 10, 22))  # type: ignore[arg-type]
    (item,) = data["items"]
    assert (item["input_tokens"], item["cached_tokens"]) == (150, 70)


def test_batch_run_page_shows_cached_tokens() -> None:
    out = run_to_dict(run(input_tokens=3000, output_tokens=0, cached_tokens=2000))
    assert (out["input_tokens"], out["cached_tokens"]) == (3000, 2000)
