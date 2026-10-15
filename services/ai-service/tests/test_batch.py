from __future__ import annotations

import asyncio
from typing import Any

import pytest
from openpyxl import load_workbook
from platform_common.errors import ApiError

from app.application import batch_execute, batch_queue
from app.application import batch_runs as service
from app.core import storage
from app.core.config import get_settings
from app.repositories import batch_runs as repo
from app.repositories import prompts as prompt_repo
from app.worker import runner
from tests.helpers import ACTOR, PROMPT_ID, RUN_ID, FakeSession, fake_stream, noop, run, template, xlsx


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "enqueue_event", noop)
    monkeypatch.setattr(repo, "mark_stale_interrupted", noop)
    monkeypatch.setattr(get_settings(), "baidu_api_key", "k")


def _returns(module: Any, name: str, value: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(*_: Any, **__: Any) -> Any:
        return value

    monkeypatch.setattr(module, name, fake)


async def test_start_snapshots_template_files_and_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "get", template(excel_name="a.xlsx", model_id=""), monkeypatch)
    _returns(repo, "active_for_prompt", None, monkeypatch)
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲"]]))
    session = FakeSession()
    data = await service.start_run(
        session,
        ACTOR,
        {"prompt_id": PROMPT_ID, "model_id": "baidu-deepseek-v3.2", "thinking": True, "limit": 10},  # type: ignore[arg-type]
    )
    assert (data["status"], data["row_limit"], data["thinking"], data["model_id"]) == (
        "queued",
        10,
        True,
        "baidu-deepseek-v3.2",
    )
    assert (storage.run_dir(data["id"]) / "source.xlsx").is_file()
    assert data["can_stop"] and not data["can_delete"]


async def test_start_refuses_without_excel_or_when_same_template_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "get", template(), monkeypatch)
    with pytest.raises(ApiError, match="未上传 Excel"):
        await service.start_run(FakeSession(), ACTOR, {"prompt_id": PROMPT_ID})  # type: ignore[arg-type]
    _returns(prompt_repo, "get", template(excel_name="a.xlsx"), monkeypatch)
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲"]]))
    _returns(repo, "active_for_prompt", run(status="running", done_count=3, total_count=9), monkeypatch)
    with pytest.raises(ApiError) as conflict:
        await service.start_run(FakeSession(), ACTOR, {"prompt_id": PROMPT_ID})  # type: ignore[arg-type]
    assert conflict.value.http_status == 409 and "3/9" in conflict.value.message


async def test_stop_cancels_queued_and_flags_running(monkeypatch: pytest.MonkeyPatch) -> None:
    queued = run(status="queued")
    _returns(repo, "get", queued, monkeypatch)
    assert (await service.stop_run(FakeSession(), ACTOR, RUN_ID))["status"] == "cancelled"  # type: ignore[arg-type]
    running = run(status="running")
    _returns(repo, "get", running, monkeypatch)
    data = await service.stop_run(FakeSession(), ACTOR, RUN_ID)  # type: ignore[arg-type]
    assert (data["status"], data["cancel_requested"]) == ("stopping", True)
    _returns(repo, "get", run(status="done"), monkeypatch)
    with pytest.raises(ApiError, match="已结束"):
        await service.stop_run(FakeSession(), ACTOR, RUN_ID)  # type: ignore[arg-type]


async def test_delete_only_after_finish_and_removes_files(monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(repo, "get", run(status="running"), monkeypatch)
    with pytest.raises(ApiError, match="仍在运行"):
        await service.delete_run(FakeSession(), ACTOR, RUN_ID)  # type: ignore[arg-type]
    _returns(repo, "get", run(status="done"), monkeypatch)
    monkeypatch.setattr(repo, "delete", noop)
    storage.write_atomic(storage.run_file(RUN_ID, "log"), b"x")
    await service.delete_run(FakeSession(), ACTOR, RUN_ID)  # type: ignore[arg-type]
    assert not storage.run_dir(RUN_ID).exists()


async def test_list_and_progress_and_download(monkeypatch: pytest.MonkeyPatch) -> None:
    finished = run(status="done", total_count=4, done_count=4, input_tokens=1500, output_tokens=500)
    _returns(repo, "page", ([finished], 1), monkeypatch)
    page = await service.list_runs(FakeSession(), page=0, page_size=500)  # type: ignore[arg-type]
    assert (page["page"], page["page_size"], page["total"]) == (1, 100, 1)
    item = page["items"][0]
    assert (item["percent"], item["total_tokens_kilo"], item["can_delete"]) == (100, 2.0, True)
    _returns(repo, "get", run(status="running", total_count=4, done_count=1), monkeypatch)
    assert (await service.get_run(FakeSession(), RUN_ID))["percent"] == 25  # type: ignore[arg-type]
    storage.write_atomic(storage.run_file(RUN_ID, "result"), b"xlsx")
    content, name = await service.download(FakeSession(), ACTOR, RUN_ID, "result")  # type: ignore[arg-type]
    assert (content, name) == (b"xlsx", "企业行业-结果.xlsx")


class _Recorder:
    def __init__(self, cancel_after: int | None = None) -> None:
        self.updates: list[dict[str, Any]] = []
        self.cancel_after = cancel_after

    async def update(self, _: Any, run_id: str, values: dict[str, Any]) -> None:
        self.updates.append(values)

    async def cancel(self, *_: Any) -> bool:
        return self.cancel_after is not None


def _prepare_execution(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder, item: Any) -> None:
    run_dir = storage.run_dir(RUN_ID)
    storage.remove_tree(run_dir)
    storage.write_atomic(run_dir / "source.xlsx", xlsx([["名称", "行业"], ["甲", "旧"], ["乙", "旧"], ["丙", "旧"]]))
    storage.write_atomic(run_dir / "code.txt", "码".encode())
    monkeypatch.setattr(batch_execute, "SessionLocal", FakeSession)
    _returns(repo, "get", item, monkeypatch)
    monkeypatch.setattr(repo, "update_fields", recorder.update)
    monkeypatch.setattr(repo, "cancel_flag", recorder.cancel)
    monkeypatch.setattr(get_settings(), "batch_concurrency", 2)


async def test_execute_runs_rows_and_builds_result(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run(output_fields="行业", row_limit=2))
    events = [{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 1000, "output_tokens": 1000}}]
    monkeypatch.setattr(batch_execute, "stream_responses", fake_stream(events))
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert (final["status"], final["done_count"], final["failed_count"]) == ("done", 2, 0)
    assert (final["input_tokens"], str(final["inference_cost"])) == (2000, "0.012000")
    sheet = load_workbook(storage.run_file(RUN_ID, "result")).active
    assert sheet is not None
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    assert rows[0][:4] == ["名称", "行业", "myid", "行业_结果"]
    assert [row[:4] for row in rows[1:]] == [["甲", "旧", "a1000001", "制造"], ["乙", "旧", "a1000002", "制造"]]
    assert "结束：done" in storage.run_file(RUN_ID, "log").read_text(encoding="utf-8")


async def test_execute_records_failures_and_honors_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(cancel_after=0)
    _prepare_execution(monkeypatch, recorder, run())
    monkeypatch.setattr(batch_execute, "PROGRESS_SECONDS", 0)

    async def slow(*_: Any, **__: Any) -> Any:
        await asyncio.sleep(0.05)
        yield {"error": "限流"}

    monkeypatch.setattr(batch_execute, "stream_responses", slow)
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert final["status"] == "cancelled" and final["failed_count"] == final["done_count"] >= 1
    assert final["done_count"] < 3
    assert storage.run_file(RUN_ID, "failed").is_file()


async def test_execute_marks_failure_when_snapshot_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run())
    storage.remove_tree(storage.run_dir(RUN_ID))
    await batch_execute.execute(RUN_ID)
    assert recorder.updates[-1]["status"] == "failed" and "快照不存在" in recorder.updates[-1]["error_message"]


async def test_call_counts_search_events_when_usage_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.llm_models import find_model

    events = [{"tool_event": {"stage": "web_search_in_progress"}}] * 2 + [{"text": "x"}]
    monkeypatch.setattr(batch_execute, "stream_responses", fake_stream(events))
    model = find_model("deepseek-v4-flash")
    assert model is not None
    result = await batch_execute.call_model_once(model, "问", False, None)  # type: ignore[arg-type]
    assert (result.text, result.search_calls, result.error) == ("x", 2, "")


async def test_queue_claims_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch_queue, "SessionLocal", FakeSession)
    _returns(repo, "claim_next", run(), monkeypatch)
    assert await batch_queue.claim_next() == RUN_ID
    _returns(repo, "running_ids", [RUN_ID], monkeypatch)
    recorder = _Recorder()
    monkeypatch.setattr(repo, "update_fields", recorder.update)
    assert await batch_queue.recover_orphans() == 1
    assert recorder.updates[0]["status"] == "interrupted"
    await batch_queue.beat()


async def test_worker_consumes_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = iter([RUN_ID, None])
    executed: list[str] = []
    stop = asyncio.Event()

    async def claim() -> str | None:
        value = next(claims, None)
        if value is None:
            await asyncio.sleep(0)  # 让刚认领的任务先跑起来，再要求退出
            stop.set()
        return value

    async def execute(run_id: str) -> None:
        executed.append(run_id)

    async def recover() -> int:
        return 1

    monkeypatch.setattr(runner, "claim_next", claim)
    monkeypatch.setattr(runner, "execute", execute)
    monkeypatch.setattr(runner, "recover_orphans", recover)
    await asyncio.wait_for(runner.consume(stop), timeout=5)
    assert executed == [RUN_ID]


def test_history_filters_combine_fields_and_map_run_mode() -> None:
    def sql(filters: dict[str, Any]) -> list[str]:
        return [str(cond.compile(compile_kwargs={"literal_binds": True})) for cond in repo._conditions(filters)]

    assert sql({}) == []
    assert sql({"run_mode": ["test"]}) == ["ai_batch_runs.row_limit > 0"]
    assert sql({"run_mode": ["all"]}) == ["ai_batch_runs.row_limit = 0"]
    assert sql({"run_mode": ["test", "all"], "status": []}) == []
    combined = sql({"prompt_title": ["政策解读", "政策市场机会"], "created_by_name": ["张三"], "status": ["done"]})
    assert combined == [
        "ai_batch_runs.prompt_title IN ('政策解读', '政策市场机会')",
        "ai_batch_runs.created_by_name IN ('张三')",
        "ai_batch_runs.status IN ('done')",
    ]


async def test_list_passes_filters_and_reports_run_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def page(*_: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return [run(row_limit=10), run(row_limit=0)], 2

    monkeypatch.setattr(repo, "page", page)
    data = await service.list_runs(FakeSession(), page=1, page_size=15, filters={"run_mode": ["test"]})  # type: ignore[arg-type]
    assert seen["filters"] == {"run_mode": ["test"]}
    assert [item["run_mode"] for item in data["items"]] == ["test", "all"]
    _returns(repo, "distinct_values", ["甲"], monkeypatch)
    assert await service.filter_options(FakeSession()) == {"prompt_title": ["甲"], "created_by_name": ["甲"]}  # type: ignore[arg-type]
