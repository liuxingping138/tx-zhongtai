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

from app.application import batch_execute, batch_queue, batch_runs, prompts
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.domain.models import BatchRun, OutboxEvent, PromptTemplate
from app.repositories import batch_runs as repo
from tests.helpers import ACTOR, fake_stream, xlsx

pytestmark = pytest.mark.skipif(os.environ.get("AI_INTEGRATION") != "1", reason="需要独立 ai_test 数据库")


@pytest_asyncio.fixture(autouse=True)
async def isolated(monkeypatch: pytest.MonkeyPatch) -> Any:
    assert engine.url.database == "ai_test", "拒绝在业务数据库执行破坏性测试"
    monkeypatch.setattr(get_settings(), "baidu_api_key", "integration")
    async with SessionLocal() as session:
        for model in (BatchRun, PromptTemplate, OutboxEvent):
            await session.execute(delete(model))
        await session.commit()
    yield
    await engine.dispose()


async def _template_with_excel(rows: int = 3) -> str:
    async with SessionLocal() as session:
        data = await prompts.create_prompt(
            session,
            ACTOR,
            {"title": "集成", "content": "企业：@【名称】", "output_fields": "行业", "model_id": "baidu-deepseek-v3.2"},
        )
        await session.commit()
    async with SessionLocal() as session:
        content = xlsx([["名称"], *[[f"企业{index}"] for index in range(rows)]])
        await prompts.upload_file(session, ACTOR, data["id"], "excel", "企业.xlsx", content)
        await session.commit()
    return str(data["id"])


async def _start(prompt_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        run = await batch_runs.start_run(session, ACTOR, {"prompt_id": prompt_id})
        await session.commit()
        return run


async def test_same_template_cannot_start_twice_concurrently() -> None:
    prompt_id = await _template_with_excel()
    results = await asyncio.gather(_start(prompt_id), _start(prompt_id), return_exceptions=True)
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, ApiError) and item.http_status == 409 for item in results) == 1


async def test_parallel_claims_take_different_runs() -> None:
    first = await _start(await _template_with_excel())
    second = await _start(await _template_with_excel())
    claimed = await asyncio.gather(batch_queue.claim_next(), batch_queue.claim_next(), batch_queue.claim_next())
    assert sorted(item for item in claimed if item) == sorted([first["id"], second["id"]])
    assert claimed.count(None) == 1


async def test_stale_running_runs_become_interrupted() -> None:
    run = await _start(await _template_with_excel())
    assert await batch_queue.claim_next() == run["id"]
    async with SessionLocal() as session:
        await repo.update_fields(session, run["id"], {"heartbeat_at": utcnow() - timedelta(minutes=10)})
        await session.commit()
    async with SessionLocal() as session:
        listed = await batch_runs.list_runs(session, page=1, page_size=15)
        await session.commit()
    assert listed["items"][0]["status"] == "interrupted"


async def test_full_flow_builds_result_from_real_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _start(await _template_with_excel(rows=3))
    monkeypatch.setattr(
        batch_execute,
        "stream_responses",
        fake_stream([{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 100, "output_tokens": 50}}]),
    )
    assert await batch_queue.claim_next() == run["id"]
    await batch_execute.execute(run["id"])
    async with SessionLocal() as session:
        done = await batch_runs.get_run(session, run["id"])
    assert (done["status"], done["done_count"], done["total_count"], done["failed_count"]) == ("done", 3, 3, 0)
    assert done["files"]["result"] and done["files"]["raw"] and not done["files"]["failed"]
    sheet = load_workbook(storage.run_file(run["id"], "result")).active
    assert sheet is not None
    assert [row[2] for row in sheet.iter_rows(min_row=2, values_only=True)] == ["制造"] * 3
    async with SessionLocal() as session:
        await batch_runs.delete_run(session, ACTOR, run["id"])
        await session.commit()
    assert not storage.run_dir(run["id"]).exists()


async def test_stop_running_run_sets_flag_and_queued_run_cancels() -> None:
    queued = await _start(await _template_with_excel())
    async with SessionLocal() as session:
        assert (await batch_runs.stop_run(session, ACTOR, queued["id"]))["status"] == "cancelled"
        await session.commit()
    running = await _start(await _template_with_excel())
    await batch_queue.claim_next()
    async with SessionLocal() as session:
        stopped = await batch_runs.stop_run(session, ACTOR, running["id"])
        await session.commit()
    assert (stopped["status"], stopped["cancel_requested"]) == ("stopping", True)
    async with SessionLocal() as session:
        assert await repo.cancel_flag(session, running["id"]) is True


async def test_history_filters_on_real_rows() -> None:
    prompt_id = await _template_with_excel()
    async with SessionLocal() as session:
        await batch_runs.start_run(session, ACTOR, {"prompt_id": prompt_id, "limit": 10})
        await session.commit()
    async with SessionLocal() as session:
        tests = await batch_runs.list_runs(session, page=1, page_size=15, filters={"run_mode": ["test"]})
        full = await batch_runs.list_runs(session, page=1, page_size=15, filters={"run_mode": ["all"]})
        by_title = await batch_runs.list_runs(session, page=1, page_size=15, filters={"prompt_title": ["集成"]})
        by_other = await batch_runs.list_runs(session, page=1, page_size=15, filters={"created_by_name": ["别人"]})
        options = await batch_runs.filter_options(session)
    assert (tests["total"], full["total"], by_title["total"], by_other["total"]) == (1, 0, 1, 0)
    assert tests["items"][0]["run_mode"] == "test"
    assert options == {"prompt_title": ["集成"], "created_by_name": [ACTOR.name]}
