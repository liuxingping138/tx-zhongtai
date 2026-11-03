"""只在显式指定的全新 ai_test 库运行：真实 Postgres 上的认领、并发发起、心跳超时和完整执行。不调用大模型。"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from typing import Any

import pytest
import pytest_asyncio
from openpyxl import load_workbook
from platform_common.clock import utcnow
from platform_common.errors import ApiError
from sqlalchemy import delete

from app.application import (
    batch_execute,
    batch_queue,
    batch_runs,
    batch_start,
    billing,
    prompts,
    releases,
    row_asking,
    sample_runs,
)
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.domain.categories import FULL_ACCESS, CategoryAccess
from app.domain.models import BatchRun, CallUsage, OutboxEvent, PromptTemplate, RunCost, TemplateRelease
from app.repositories import batch_runs as repo
from tests.helpers import ACTOR, fake_stream, run, xlsx

pytestmark = pytest.mark.skipif(os.environ.get("AI_INTEGRATION") != "1", reason="需要独立 ai_test 数据库")


@pytest_asyncio.fixture(autouse=True)
async def isolated(monkeypatch: pytest.MonkeyPatch) -> Any:
    assert engine.url.database == "ai_test", "拒绝在业务数据库执行破坏性测试"
    monkeypatch.setattr(get_settings(), "baidu_api_key", "integration")
    async with SessionLocal() as session:
        for model in (BatchRun, CallUsage, PromptTemplate, TemplateRelease, OutboxEvent, RunCost):
            await session.execute(delete(model))
        await session.commit()
    yield
    await engine.dispose()


async def _template_with_excel(rows: int = 3) -> str:
    async with SessionLocal() as session:
        data = await prompts.create_prompt(
            session,
            ACTOR,
            FULL_ACCESS,
            {
                "title": "集成",
                "category": "policy",
                "content": "企业：@【名称】",
                "output_fields": "行业",
                "model_id": "baidu-deepseek-v3.2",
            },
        )
        await session.commit()
    async with SessionLocal() as session:
        content = xlsx([["名称"], *[[f"企业{index}"] for index in range(rows)]])
        await prompts.upload_file(session, ACTOR, FULL_ACCESS, data["id"], "excel", ("企业.xlsx", content))
        await session.commit()
    # 批量任务只跑上线版本：先上线第 1 版。
    async with SessionLocal() as session:
        await releases.publish(session, ACTOR, FULL_ACCESS, data["id"])
        await session.commit()
    return str(data["id"])


async def _start(prompt_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        run = await batch_start.start_run(
            session,
            ACTOR,
            FULL_ACCESS,
            {"prompt_id": prompt_id},
            upload=("本次.xlsx", storage.prompt_file(prompt_id, "excel").read_bytes()),
        )
        await session.commit()
        return run


async def test_same_template_cannot_start_twice_concurrently() -> None:
    prompt_id = await _template_with_excel()
    results = await asyncio.gather(_start(prompt_id), _start(prompt_id), return_exceptions=True)
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, ApiError) and item.http_status == 409 for item in results) == 1


async def _claim_id(**kwargs: Any) -> str | None:
    claimed = await batch_queue.claim_next(**kwargs)
    return claimed[0] if claimed else None


async def test_parallel_claims_take_different_runs() -> None:
    first = await _start(await _template_with_excel())
    second = await _start(await _template_with_excel())
    claimed = await asyncio.gather(_claim_id(), _claim_id(), _claim_id())
    assert sorted(item for item in claimed if item) == sorted([first["id"], second["id"]])
    assert claimed.count(None) == 1


async def test_bulk_runs_are_skipped_when_their_slots_are_full() -> None:
    """页面批量任务占满它那份执行位后，worker 只认领样本试跑和定时打标，排在后面的批量任务等着。"""

    queued = await _start(await _template_with_excel())
    assert await _claim_id(exclude_sources=batch_queue.BULK_SOURCES) is None
    assert await _claim_id() == queued["id"]


async def test_stale_running_runs_become_interrupted() -> None:
    run = await _start(await _template_with_excel())
    assert await _claim_id() == run["id"]
    async with SessionLocal() as session:
        await repo.update_fields(session, run["id"], {"heartbeat_at": utcnow() - timedelta(minutes=10)})
        await session.commit()
    async with SessionLocal() as session:
        listed = await batch_runs.list_runs(session, FULL_ACCESS, page=1, page_size=15)
        await session.commit()
    assert listed["items"][0]["status"] == "interrupted"


async def test_full_flow_builds_result_from_real_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _start(await _template_with_excel(rows=3))
    monkeypatch.setattr(
        row_asking,
        "stream_responses",
        fake_stream([{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 100, "output_tokens": 50}}]),
    )
    assert await _claim_id() == run["id"]
    await batch_execute.execute(run["id"])
    async with SessionLocal() as session:
        done = await batch_runs.get_run(session, FULL_ACCESS, run["id"])
    assert (done["status"], done["done_count"], done["total_count"], done["failed_count"]) == ("done", 3, 3, 0)
    assert done["files"]["result"] and done["files"]["raw"] and not done["files"]["failed"]
    sheet = load_workbook(storage.run_file(run["id"], "result")).active
    assert sheet is not None
    assert [row[2] for row in sheet.iter_rows(min_row=2, values_only=True)] == ["制造"] * 3
    async with SessionLocal() as session:
        await batch_runs.delete_run(session, ACTOR, FULL_ACCESS, run["id"])
        await session.commit()
    assert not storage.run_dir(run["id"]).exists()


async def test_stop_running_run_sets_flag_and_queued_run_cancels() -> None:
    queued = await _start(await _template_with_excel())
    async with SessionLocal() as session:
        assert (await batch_runs.stop_run(session, ACTOR, FULL_ACCESS, queued["id"]))["status"] == "cancelled"
        await session.commit()
    running = await _start(await _template_with_excel())
    await _claim_id()
    async with SessionLocal() as session:
        stopped = await batch_runs.stop_run(session, ACTOR, FULL_ACCESS, running["id"])
        await session.commit()
    assert (stopped["status"], stopped["cancel_requested"]) == ("stopping", True)
    async with SessionLocal() as session:
        assert await repo.cancel_flag(session, running["id"]) is True


async def test_history_filters_on_real_rows() -> None:
    prompt_id = await _template_with_excel()
    async with SessionLocal() as session:
        await batch_start.start_run(
            session,
            ACTOR,
            FULL_ACCESS,
            {"prompt_id": prompt_id, "limit": 2},
            upload=("本次.xlsx", storage.prompt_file(prompt_id, "excel").read_bytes()),
        )
        await session.commit()
    async with SessionLocal() as session:
        tests = await batch_runs.list_runs(session, FULL_ACCESS, page=1, page_size=15, filters={"run_mode": ["test"]})
        full = await batch_runs.list_runs(session, FULL_ACCESS, page=1, page_size=15, filters={"run_mode": ["all"]})
        by_title = await batch_runs.list_runs(
            session, FULL_ACCESS, page=1, page_size=15, filters={"prompt_title": ["集成"]}
        )
        by_other = await batch_runs.list_runs(
            session, FULL_ACCESS, page=1, page_size=15, filters={"created_by_name": ["别人"]}
        )
        by_category = await batch_runs.list_runs(
            session, FULL_ACCESS, page=1, page_size=15, filters={"prompt_category": ["tender"]}
        )
        hidden = await batch_runs.list_runs(
            session, CategoryAccess(frozenset({"tender"}), frozenset()), page=1, page_size=15
        )
        options = await batch_runs.filter_options(session, FULL_ACCESS)
    assert (tests["total"], full["total"], by_title["total"], by_other["total"]) == (1, 0, 1, 0)
    # 政策类的任务：按招投标筛不到；只能看招投标类的人整页都看不到。
    assert (by_category["total"], hidden["total"]) == (0, 0)
    assert tests["items"][0]["run_mode"] == "test"
    assert options == {"prompt_title": ["集成"], "created_by_name": [ACTOR.name]}


async def test_billing_groups_batches_pipelines_and_calls_by_beijing_day() -> None:
    from datetime import UTC, date, datetime
    from decimal import Decimal

    late = datetime(2026, 10, 21, 17, 30, tzinfo=UTC)  # 北京时间 10-22 01:30
    async with SessionLocal() as session:
        session.add(run(id="1" * 32, created_at=late, inference_cost=Decimal("0.2"), search_cost=Decimal("0.05")))
        session.add(run(id="2" * 32, created_at=late, inference_cost=Decimal("0.1"), input_tokens=7))
        session.add(
            run(id="3" * 32, created_at=late, source="pipeline", created_by_name="政策AI打标·政策解读",
                inference_cost=Decimal("0.3"))
        )  # fmt: skip
        session.add(run(id="4" * 32, created_at=late, source="sample", inference_cost=Decimal("0.04")))
        session.add(run(id="6" * 32, created_at=late))  # 排队就取消、一分钱没花：不算一次
        for index, kind in enumerate(("chat", "chat", "trial")):
            session.add(
                CallUsage(id=f"{index}" * 32, kind=kind, model_id="m", model_name="百度-DeepSeek-V3.2",
                          inference_cost=Decimal("0.01"), created_at=late)
            )  # fmt: skip
        await session.commit()
    async with SessionLocal() as session:
        data = await billing.daily(session, date(2026, 10, 22), date(2026, 10, 22))
        earlier = await billing.daily(session, date(2026, 10, 21), date(2026, 10, 21))
    rows = {(item["purpose"], item["calls"], item["cost"], item["input_tokens"]) for item in data["items"]}
    assert rows == {
        ("批量任务", 2, "0.350000", 7),
        ("样本试跑", 1, "0.040000", 0),
        ("政策AI打标·政策解读", 1, "0.300000", 0),
        ("多轮对话（已下线）", 2, "0.020000", 0),
        ("试发", 1, "0.010000", 0),
    }
    assert {item["day"] for item in data["items"]} == {"2026-10-22"} and earlier["items"] == []


async def test_rerun_costs_land_on_the_day_they_were_spent() -> None:
    """几天后重跑失败的行：钱记到重跑那天，不改发起那天已经看过的数；同一天多次写进度累加在一行。"""

    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.application.run_costs import Spend, book

    started = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)  # 北京 10-21
    async with SessionLocal() as session:
        session.add(run(id="5" * 32, created_at=started, inference_cost=Decimal("0.6")))
        await book(session, "5" * 32, {date(2026, 10, 21): Spend(10, 5, 0, Decimal("0.1"), Decimal(0))})
        for part in ("0.2", "0.3"):
            await book(session, "5" * 32, {date(2026, 10, 23): Spend(1, 1, 0, Decimal(part), Decimal(0))})
        await session.commit()
    async with SessionLocal() as session:
        first = await billing.daily(session, date(2026, 10, 21), date(2026, 10, 21))
        later = await billing.daily(session, date(2026, 10, 23), date(2026, 10, 23))
        both = await billing.daily(session, date(2026, 10, 21), date(2026, 10, 23))
    assert [(item["calls"], item["cost"], item["input_tokens"]) for item in first["items"]] == [(1, "0.100000", 10)]
    assert [(item["calls"], item["cost"], item["input_tokens"]) for item in later["items"]] == [(1, "0.500000", 2)]
    assert sorted(item["cost"] for item in both["items"]) == ["0.100000", "0.500000"]


async def test_sample_runs_stay_on_the_template_page() -> None:
    """样本试跑跑草稿，和正式任务互不阻挡；不进批量任务列表，模板上能看到最近一次。"""

    prompt_id = await _template_with_excel(rows=3)
    async with SessionLocal() as session:
        await prompts.update_prompt(
            session,
            ACTOR,
            FULL_ACCESS,
            prompt_id,
            {"title": "集成", "category": "policy", "content": "草稿：@【名称】", "output_fields": "行业",
             "model_id": "baidu-deepseek-v3.2", "version": 2},
        )  # fmt: skip
        await session.commit()
    formal = await _start(prompt_id)
    async with SessionLocal() as session:
        first = await sample_runs.start(session, ACTOR, FULL_ACCESS, prompt_id, {"limit": 2})
        await session.commit()
    async with SessionLocal() as session:
        with pytest.raises(ApiError) as busy:
            await sample_runs.start(session, ACTOR, FULL_ACCESS, prompt_id, {"limit": 2})
    assert busy.value.http_status == 409
    async with SessionLocal() as session:
        await sample_runs.stop(session, ACTOR, FULL_ACCESS, prompt_id)
        await session.commit()
    async with SessionLocal() as session:
        second = await sample_runs.start(session, ACTOR, FULL_ACCESS, prompt_id, {"limit": 3})
        await session.commit()
    async with SessionLocal() as session:
        listed = await batch_runs.list_runs(session, FULL_ACCESS, page=1, page_size=15)
        latest = await sample_runs.view(session, FULL_ACCESS, prompt_id)
        template = next(item for item in await prompts.list_prompts(session, FULL_ACCESS) if item["id"] == prompt_id)
    assert [item["id"] for item in listed["items"]] == [formal["id"]]
    assert formal["release_no"] == 1 and first["run"]["id"] != second["run"]["id"]
    assert latest["run"]["id"] == second["run"]["id"] and latest["rows"]["total"] == 3
    # 第 2 次默认和第 1 次比；两次复制的是同一份测试样本。
    assert [item["no"] for item in latest["history"]] == [2, 1]
    assert latest["compare"]["run"]["id"] == first["run"]["id"] and latest["compare"]["same_input"] is True
    assert template["sample"]["id"] == second["run"]["id"] and template["sample"]["current"] is True
    assert template["release"]["unreleased_changes"] == ["提示词内容"]


async def test_batch_can_run_the_saved_draft() -> None:
    """批量任务可以不等上线：跑草稿的任务记下草稿保存时间，没有上线版本号。"""

    prompt_id = await _template_with_excel()
    async with SessionLocal() as session:
        run = await batch_start.start_run(
            session,
            ACTOR,
            FULL_ACCESS,
            {"prompt_id": prompt_id, "version": "draft"},
            upload=("本次.xlsx", storage.prompt_file(prompt_id, "excel").read_bytes()),
        )
        await session.commit()
    async with SessionLocal() as session:
        listed = await batch_runs.list_runs(session, FULL_ACCESS, page=1, page_size=15)
    item = listed["items"][0]
    assert (item["id"], item["release_no"]) == (run["id"], None) and item["draft_saved_at"]
