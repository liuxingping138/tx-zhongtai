from __future__ import annotations

import asyncio
from typing import Any

import pytest
from openpyxl import load_workbook
from platform_common.errors import ApiError, PermissionDeniedError

from app.application import batch_execute, batch_queue, batch_start, row_asking
from app.application import batch_runs as service
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS, CategoryAccess
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


async def test_stop_cancels_queued_and_flags_running(monkeypatch: pytest.MonkeyPatch) -> None:
    queued = run(status="queued")
    _returns(repo, "get", queued, monkeypatch)
    assert (await service.stop_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID))["status"] == "cancelled"  # type: ignore[arg-type]
    running = run(status="running")
    _returns(repo, "get", running, monkeypatch)
    data = await service.stop_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert (data["status"], data["cancel_requested"]) == ("stopping", True)
    _returns(repo, "get", run(status="done"), monkeypatch)
    with pytest.raises(ApiError, match="已结束"):
        await service.stop_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]


async def test_delete_only_after_finish_and_removes_files(monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(repo, "get", run(status="running"), monkeypatch)
    with pytest.raises(ApiError, match="仍在运行"):
        await service.delete_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    finished = run(status="done")
    _returns(repo, "get", finished, monkeypatch)
    storage.write_atomic(storage.run_file(RUN_ID, "log"), b"x")
    await service.delete_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert not storage.run_dir(RUN_ID).exists()
    # 只打删除标记：行还在，费用账单里这笔钱不会因为删了任务就消失。
    assert finished.deleted_at is not None


async def test_list_and_progress_and_download(monkeypatch: pytest.MonkeyPatch) -> None:
    finished = run(status="done", total_count=4, done_count=4, input_tokens=1500, output_tokens=500)
    _returns(repo, "page", ([finished], 1), monkeypatch)
    page = await service.list_runs(FakeSession(), FULL_ACCESS, page=0, page_size=500)  # type: ignore[arg-type]
    assert (page["page"], page["page_size"], page["total"]) == (1, 100, 1)
    item = page["items"][0]
    assert (item["percent"], item["total_tokens_kilo"], item["can_delete"]) == (100, 2.0, True)
    _returns(repo, "get", run(status="running", total_count=4, done_count=1), monkeypatch)
    assert (await service.get_run(FakeSession(), FULL_ACCESS, RUN_ID))["percent"] == 25  # type: ignore[arg-type]
    storage.write_atomic(storage.run_file(RUN_ID, "result"), b"xlsx")
    path, name = await service.download(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID, "result")  # type: ignore[arg-type]
    assert (path.read_bytes(), name) == (b"xlsx", "企业行业-结果.xlsx")


class _Recorder:
    def __init__(self, cancel_after: int | None = None) -> None:
        self.updates: list[dict[str, Any]] = []
        self.cancel_after = cancel_after
        # 任务在库里还是不是运行中：被纠正成「中断」后再点重跑排回队列时为 False。
        self.running = True

    async def update(self, _: Any, run_id: str, values: dict[str, Any]) -> None:
        self.updates.append(values)

    async def update_running(self, _: Any, run_id: str, values: dict[str, Any], also: Any = ()) -> bool:
        if self.running:
            self.updates.append(values)
        return self.running

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
    monkeypatch.setattr(repo, "update_if_running", recorder.update_running)
    monkeypatch.setattr(repo, "cancel_flag", recorder.cancel)
    monkeypatch.setattr(get_settings(), "batch_concurrency", 2)


async def test_execute_runs_rows_and_builds_result(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run(output_fields="行业", row_limit=2))
    events = [{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 1000, "output_tokens": 1000}}]
    monkeypatch.setattr(row_asking, "stream_responses", fake_stream(events))
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

    monkeypatch.setattr(row_asking, "stream_responses", slow)
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
    from app.application.model_configs import to_model
    from tests.helpers import ai_model

    events = [{"tool_event": {"stage": "web_search_in_progress"}}] * 2 + [{"text": "x"}]
    monkeypatch.setattr(row_asking, "stream_responses", fake_stream(events))
    model = to_model(ai_model())
    result = await row_asking.call_model_once(model, "问", False, None)  # type: ignore[arg-type]
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
    data = await service.list_runs(FakeSession(), FULL_ACCESS, page=1, page_size=15, filters={"run_mode": ["test"]})  # type: ignore[arg-type]
    assert seen["filters"] == {"run_mode": ["test"]}
    assert [item["run_mode"] for item in data["items"]] == ["test", "all"]
    _returns(repo, "distinct_values", ["甲"], monkeypatch)
    assert await service.filter_options(FakeSession(), FULL_ACCESS) == {
        "prompt_title": ["甲"],
        "created_by_name": ["甲"],
    }  # type: ignore[arg-type]


def _model() -> Any:
    from app.application.model_configs import to_model
    from tests.helpers import sample_models

    return to_model(sample_models()[1])


def _sequence(monkeypatch: pytest.MonkeyPatch, answers: list[list[dict[str, Any]]]) -> list[int]:
    calls: list[int] = []

    async def stream(*_: Any, **__: Any) -> Any:
        calls.append(1)
        for event in answers[min(len(calls), len(answers)) - 1]:
            yield event

    monkeypatch.setattr(row_asking, "stream_responses", stream)
    monkeypatch.setattr(row_asking, "RETRY_DELAYS", (0.0, 0.0))
    return calls


USAGE = {"usage": {"input_tokens": 100, "output_tokens": 10}}


async def test_ask_row_backs_off_on_retryable_errors_and_sums_spent_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    limited = [{"error": "HTTP 429", "retryable": True}]
    calls = _sequence(monkeypatch, [limited, [USAGE, *limited], [{"text": '[{"行业":"制造"}]'}, USAGE]])
    result = await row_asking.ask_row(_model(), "问", False, ["行业"], None)  # type: ignore[arg-type]
    assert (result.error, result.attempts, result.input_tokens, len(calls)) == ("", 3, 200, 3)
    calls = _sequence(monkeypatch, [limited])
    result = await row_asking.ask_row(_model(), "问", False, ["行业"], None)  # type: ignore[arg-type]
    assert (result.error, result.failure_kind, len(calls)) == ("HTTP 429", "调用失败", 3)
    calls = _sequence(monkeypatch, [[{"error": "HTTP 400", "retryable": False}]])
    result = await row_asking.ask_row(_model(), "问", False, ["行业"], None)  # type: ignore[arg-type]
    assert (result.error, len(calls)) == ("HTTP 400", 1)


async def test_ask_row_reasks_once_when_answer_has_no_output_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _sequence(monkeypatch, [[{"text": "我觉得是制造业"}, USAGE], [{"text": '[{"行业":"制造"}]'}, USAGE]])
    result = await row_asking.ask_row(_model(), "问", False, ["行业"], None)  # type: ignore[arg-type]
    assert (result.error, result.attempts, result.output_tokens, len(calls)) == ("", 2, 20, 2)
    calls = _sequence(monkeypatch, [[{"text": "我觉得是制造业"}]])
    result = await row_asking.ask_row(_model(), "问", False, ["行业"], None)  # type: ignore[arg-type]
    assert result.format_error and "行业" in result.error and len(calls) == 2
    calls = _sequence(monkeypatch, [[{"text": "随便答"}]])
    result = await row_asking.ask_row(_model(), "问", False, [], None)  # type: ignore[arg-type]
    assert (result.error, len(calls)) == ("", 1)


async def test_execute_resumes_and_only_asks_unfinished_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.application.batch_output import FORMAT_ERROR_PREFIX, RowResult, append_raw, start_raw

    recorder = _Recorder()
    previous = run(status="queued", total_count=3, done_count=2, failed_count=1, input_tokens=500, output_tokens=50)
    _prepare_execution(monkeypatch, recorder, previous)
    raw = storage.run_file(RUN_ID, "raw")
    start_raw(raw)
    for myid, text, error in (("a1000001", '[{"行业":"旧答"}]', ""), ("a1000002", "", f"{FORMAT_ERROR_PREFIX}：x")):
        append_raw(raw, RowResult(myid, "问", text, 0, 0, 0, error, 0.0).raw_row("模型"))
    storage.write_atomic(storage.run_file(RUN_ID, "failed"), b"old")
    calls = _sequence(monkeypatch, [[{"text": '[{"行业":"新答"}]'}, USAGE]])
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert len(calls) == 2
    assert (final["status"], final["done_count"], final["failed_count"], final["format_failed_count"]) == (
        "done",
        3,
        0,
        0,
    )
    assert (final["input_tokens"], final["output_tokens"]) == (700, 70)
    assert not storage.run_file(RUN_ID, "failed").exists()
    sheet = load_workbook(storage.run_file(RUN_ID, "result")).active
    assert sheet is not None
    assert [row[3] for row in sheet.iter_rows(min_row=2, values_only=True)] == ["旧答", "新答", "新答"]
    assert "续跑 2 条（共 3 条，已成功 1 条）" in storage.run_file(RUN_ID, "log").read_text(encoding="utf-8")


async def test_execute_keeps_old_failures_for_rows_not_reached_after_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.application.batch_output import RowResult, append_raw, start_raw

    recorder = _Recorder(cancel_after=0)
    _prepare_execution(monkeypatch, recorder, run(total_count=3, done_count=3, failed_count=3))
    monkeypatch.setattr(batch_execute, "PROGRESS_SECONDS", 0)
    raw = storage.run_file(RUN_ID, "raw")
    start_raw(raw)
    for index in range(1, 4):
        append_raw(raw, RowResult(f"a100000{index}", "问", "", 0, 0, 0, "超时", 0.0).raw_row("模型"))

    async def slow(*_: Any, **__: Any) -> Any:
        await asyncio.sleep(0.05)
        yield {"text": '[{"行业":"制造"}]'}

    monkeypatch.setattr(row_asking, "stream_responses", slow)
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert final["status"] == "cancelled" and final["done_count"] == 3
    assert 1 <= final["failed_count"] < 3


async def test_retry_requeues_finished_run_with_pending_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    storage.write_atomic(storage.run_dir(RUN_ID) / "source.xlsx", xlsx([["名称"], ["甲"]]))
    _returns(repo, "active_for_prompt", None, monkeypatch)
    finished = run(status="interrupted", total_count=10, done_count=7, failed_count=2, error_message="中断")
    _returns(repo, "get", finished, monkeypatch)
    _returns(prompt_repo, "get", template(), monkeypatch)  # 重跑和发起一样先锁模板行
    listed = service.to_dict(finished)
    assert (listed["pending_count"], listed["can_retry"]) == (5, True)
    data = await service.retry_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert (data["status"], data["error_message"], data["can_retry"], data["pending_count"]) == ("queued", "", False, 0)

    _returns(repo, "get", run(status="running", total_count=3), monkeypatch)
    with pytest.raises(ApiError, match="仍在运行"):
        await service.retry_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    _returns(repo, "get", run(status="done", total_count=3, done_count=3), monkeypatch)
    with pytest.raises(ApiError, match="没有失败"):
        await service.retry_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    _returns(repo, "get", run(status="done", total_count=3, done_count=3, failed_count=1), monkeypatch)
    _returns(repo, "active_for_prompt", run(status="running"), monkeypatch)
    with pytest.raises(ApiError) as conflict:
        await service.retry_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert conflict.value.http_status == 409
    storage.remove_tree(storage.run_dir(RUN_ID))
    with pytest.raises(ApiError, match="快照"):
        await service.retry_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]


async def test_read_only_category_can_view_runs_but_not_run_or_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """只读的类型能看进度、下载结果，不能运行、重跑、停止、删除——这些都会花钱或改数据。"""

    _returns(repo, "get", run(status="running", total_count=4, done_count=1), monkeypatch)
    _returns(prompt_repo, "get", template(excel_name="a.xlsx"), monkeypatch)
    reader = CategoryAccess(readable=frozenset({"policy"}), editable=frozenset())
    assert (await service.get_run(FakeSession(), reader, RUN_ID))["prompt_category_name"] == "政策"  # type: ignore[arg-type]
    for call in (
        batch_start.start_run(FakeSession(), ACTOR, reader, {"prompt_id": PROMPT_ID}),  # type: ignore[arg-type]
        service.stop_run(FakeSession(), ACTOR, reader, RUN_ID),  # type: ignore[arg-type]
        service.retry_run(FakeSession(), ACTOR, reader, RUN_ID),  # type: ignore[arg-type]
        service.delete_run(FakeSession(), ACTOR, reader, RUN_ID),  # type: ignore[arg-type]
    ):
        with pytest.raises(PermissionDeniedError):
            await call
    with pytest.raises(PermissionDeniedError):
        await service.get_run(FakeSession(), CategoryAccess(frozenset(), frozenset()), RUN_ID)  # type: ignore[arg-type]


async def test_batch_endpoints_do_not_reach_sample_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """样本试跑归模板页管：拿它的 ID 也不能用批量任务的权限删除、重跑、下载。"""

    from platform_common.errors import NotFoundError

    _returns(repo, "get", run(source="sample", status="done"), monkeypatch)
    with pytest.raises(NotFoundError):
        await service.delete_run(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert (await service.require(FakeSession(), RUN_ID, sample=True)).source == "sample"  # type: ignore[arg-type]
