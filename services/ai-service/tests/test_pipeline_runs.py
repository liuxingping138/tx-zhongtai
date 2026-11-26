from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.errors import ApiError, NotFoundError
from platform_common.internal_calls import internal_headers
from sqlalchemy.exc import IntegrityError

from app.application import batch_execute, batch_runs, pipeline_runs, prompts, releases, row_asking
from app.application.batch_output import RowResult, append_raw, build_result, start_raw
from app.application.sheets import read_run_input
from app.core import storage
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.llm_models import with_service_tier
from app.domain.models import TemplateRelease
from app.main import app
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as prompt_repo
from app.repositories import releases as release_repo
from tests.helpers import ACTOR, NOW, PROMPT_ID, RUN_ID, FakeSession, fake_stream, noop, run, template
from tests.test_batch import _prepare_execution, _Recorder

RELEASE_ID = "c" * 32


def _release(**overrides: Any) -> TemplateRelease:
    values: dict[str, Any] = {
        "id": RELEASE_ID,
        "prompt_id": PROMPT_ID,
        "release_no": 3,
        "title": "政策类型判断",
        "category": "policy",
        "content": "标题：@【政策标题】\n@【上传码表】",
        "output_fields": "政策类型名称",
        "model_id": "baidu-deepseek-v3.2",
        "code_table": "policy_types",
        "code_name": "",
        "released_at": NOW,
        "released_by_id": "u1",
        "released_by_name": "管理员",
    }
    values.update(overrides)
    return TemplateRelease(**values)


@pytest.fixture
def online(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """模板已上线第 3 版；草稿内容不同，流水线必须用上线版本。"""

    added: list[Any] = []

    async def get(*_: Any, **__: Any) -> Any:
        return template(content="草稿：还没上线的改动", release_id=RELEASE_ID)

    async def by_ids(_session: Any, ids: list[str]) -> dict[str, TemplateRelease]:
        return {RELEASE_ID: _release()} if RELEASE_ID in ids else {}

    async def fetch(_name: str) -> str:
        return "政策类型名称\n信息化建设类"

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(release_repo, "by_ids", by_ids)
    monkeypatch.setattr(releases, "fetch_code_table", fetch)
    monkeypatch.setattr(pipeline_runs, "enqueue_event", noop)
    monkeypatch.setattr(run_repo, "add", lambda _session, item: added.append(item))
    monkeypatch.setattr(get_settings(), "baidu_api_key", "k")
    return added


async def test_pipeline_run_uses_the_release_flex_tier_and_cost_limit(online: list[Any]) -> None:
    long_text = "字" * 120_000
    rows = [{"源ID": "p1", "政策标题": "甲", "政策正文": long_text}, {"源ID": "p2", "政策标题": "乙"}]
    data = await pipeline_runs.create(FakeSession(), ACTOR, {"prompt_id": PROMPT_ID, "rows": rows, "cost_limit": "5"})  # type: ignore[arg-type]
    created = online[0]
    assert (created.prompt_content, created.release_no, created.source) == (_release().content, 3, "pipeline")
    assert (created.service_tier, created.cost_limit, data["status"]) == ("flex", Decimal(5), "queued")
    snapshot = storage.run_dir(created.id)
    assert (snapshot / "code.txt").read_text(encoding="utf-8").endswith("信息化建设类")
    headers, written = read_run_input(snapshot)
    # 正文全文照存（十几万字也不截断，Excel 单元格放不下才改存 JSON）；表头按出现顺序，缺列由执行时补空。
    assert headers == ["源ID", "政策标题", "政策正文"]
    assert written[0]["政策正文"] == long_text and written[1] == {"源ID": "p2", "政策标题": "乙"}
    assert not (snapshot / "source.xlsx").exists()


async def test_pipeline_run_refuses_offline_templates_and_bad_rows(
    online: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ApiError, match="源ID"):
        await pipeline_runs.create(FakeSession(), ACTOR, {"prompt_id": PROMPT_ID, "rows": [{"政策标题": "甲"}]})  # type: ignore[arg-type]

    async def draft(*_: Any, **__: Any) -> Any:
        return template()

    monkeypatch.setattr(prompt_repo, "get", draft)
    with pytest.raises(ApiError, match="还没有上线"):
        await pipeline_runs.create(FakeSession(), ACTOR, {"prompt_id": PROMPT_ID, "rows": [{"源ID": "p"}]})  # type: ignore[arg-type]
    assert online == []


async def test_results_map_back_to_source_ids_with_expanded_items_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    async def finished(*_: Any, **__: Any) -> Any:
        return run(status="done", output_fields="行业|场景")

    monkeypatch.setattr(run_repo, "get", finished)
    directory = storage.run_dir(RUN_ID)
    storage.remove_tree(directory)
    rows = [{"源ID": f"p{i}"} for i in range(3)]
    storage.write_atomic(directory / storage.ROWS_FILE, json.dumps({"headers": ["源ID"], "rows": rows}).encode())
    raw = storage.run_file(RUN_ID, "raw")
    start_raw(raw)
    answer = '[{"行业":"教育","场景":"智慧校园"},{"行业":"医卫","场景":"智慧医院"}]'
    blank: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "search_calls": 0, "elapsed": 0.0}
    append_raw(raw, RowResult(myid="a1000001", prompt="", text=answer, error="", **blank).raw_row("m"))
    append_raw(raw, RowResult(myid="a1000002", prompt="", text="", error="限流", **blank).raw_row("m"))
    data = await pipeline_runs.results(FakeSession(), RUN_ID)  # type: ignore[arg-type]
    assert data["items"] == [
        {
            "source_id": "p0",
            "items": [{"行业": "教育", "场景": "智慧校园"}, {"行业": "医卫", "场景": "智慧医院"}],
            "error": "",
        },
        {"source_id": "p1", "items": [], "error": "限流"},
        {"source_id": "p2", "items": [], "error": "未执行（任务停止或中断）"},
    ]

    async def running(*_: Any, **__: Any) -> Any:
        return run(status="running")

    monkeypatch.setattr(run_repo, "get", running)
    with pytest.raises(ApiError, match="还在运行"):
        await pipeline_runs.results(FakeSession(), RUN_ID)  # type: ignore[arg-type]


async def test_execution_stops_itself_at_the_cost_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run(output_fields="行业", cost_limit=Decimal("0.001")))
    monkeypatch.setattr(get_settings(), "batch_concurrency", 1)
    events = [{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 1000, "output_tokens": 1000}}]
    monkeypatch.setattr(row_asking, "stream_responses", fake_stream(events))
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert (final["status"], final["done_count"]) == ("cancelled", 1)
    assert "费用上限" in final["error_message"]


def test_flex_tier_only_applies_where_the_endpoint_and_prices_support_it() -> None:
    from app.application.model_configs import to_model
    from tests.helpers import ai_model, sample_models

    flexible = to_model(
        ai_model(service_tier="auto", flex_input_price=Decimal("0.1"), flex_output_price=Decimal("0.2"))
    )
    assert with_service_tier(flexible, "flex").service_tier == "flex"
    assert with_service_tier(flexible, "").service_tier == "auto"
    no_param = to_model(ai_model(service_tier="", flex_input_price=Decimal("0.1"), flex_output_price=Decimal("0.2")))
    no_price = to_model(ai_model(service_tier="auto", flex_input_price=None, flex_output_price=None))
    assert with_service_tier(no_param, "flex").service_tier == ""
    assert with_service_tier(no_price, "flex").service_tier == "auto"
    assert sample_models()


def test_internal_routes_reject_unknown_callers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db() -> Any:
        yield FakeSession()

    async def nothing(*_: Any, **__: Any) -> list[Any]:
        return []

    settings = get_settings().model_copy(update={"internal_caller_secrets": {"policy-service": "s3cret"}})
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(prompts, "online", nothing)
    try:
        client = TestClient(app)
        path = "/internal/v1/online-templates?category=policy"
        assert client.get(path).status_code == 401
        assert client.get(path, headers=internal_headers("policy-service", "wrong!")).status_code == 401
        assert client.get(path, headers=internal_headers("policy-service", "s3cret")).json()["data"] == []
    finally:
        app.dependency_overrides.clear()


async def test_pipeline_run_idempotent_replay_and_invalid_body(
    online: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_row = run(id=RUN_ID, source="pipeline")
    calls = 0

    async def fake_get(_session: Any, run_id: str, **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return existing_row if calls > 1 and run_id == RUN_ID else None

    monkeypatch.setattr(run_repo, "get", fake_get)
    rows = [{"源ID": "p1", "政策标题": "甲"}]
    first = await pipeline_runs.create(
        FakeSession(),
        ACTOR,
        {"prompt_id": PROMPT_ID, "rows": rows, "client_run_id": RUN_ID},  # type: ignore[arg-type]
    )
    second = await pipeline_runs.create(
        FakeSession(),
        ACTOR,
        {"prompt_id": PROMPT_ID, "rows": rows, "client_run_id": RUN_ID},  # type: ignore[arg-type]
    )
    assert first["id"] == RUN_ID and second["id"] == RUN_ID and len(online) == 1

    from app.api.internal import _parse_pipeline_body

    with pytest.raises(ApiError, match="请求体无效"):
        _parse_pipeline_body(b"{bad-json")


async def test_worker_lead_exits_when_lock_connection_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from contextlib import asynccontextmanager

    from app.worker import runner

    class _DeadConn:
        def __init__(self) -> None:
            self.checks = 0

        async def scalar(self, *_args: Any, **_kwargs: Any) -> Any:
            self.checks += 1
            if self.checks == 1:
                return True
            raise RuntimeError("connection lost")

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def execute(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    conn = _DeadConn()

    @asynccontextmanager
    async def _connect() -> Any:
        yield conn

    cancelled = False

    async def fake_consume(_stop: asyncio.Event) -> None:
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise

    from types import SimpleNamespace

    monkeypatch.setattr(runner, "engine", SimpleNamespace(connect=_connect))
    monkeypatch.setattr(runner, "consume", fake_consume)
    monkeypatch.setattr(runner, "beat", noop)
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.01)

    with pytest.raises(RuntimeError, match="connection lost"):
        await runner.lead(asyncio.Event())
    assert cancelled is True


def test_result_excel_cuts_cells_beyond_the_excel_limit(tmp_path: Any) -> None:
    """Excel 单元格超过 32767 字文件就打不开：结果表里截断并标明，完整内容在原始返回 CSV。"""

    from openpyxl import load_workbook

    path = tmp_path / "result.xlsx"
    rows = [{"正文": "字" * 50_000, "myid": "a1000001"}]
    answer = RowResult(
        myid="a1000001",
        prompt="",
        text='[{"行业":"教育"}]',
        error="",
        input_tokens=1,
        output_tokens=1,
        search_calls=0,
        elapsed=0.0,
    )
    build_result(path, ["正文"], rows, {"a1000001": answer}, ["行业"], "m")
    sheet = load_workbook(path).active
    assert sheet is not None
    cell = str(sheet.cell(row=2, column=1).value)
    assert len(cell) <= 32_000 and cell.endswith("已截断）")
    assert sheet.cell(row=2, column=3).value == "教育"


class _NestedSession(FakeSession):
    """带保存点的替身：conflict=True 时模拟占位撞上已经插进去的真任务（主键冲突）。"""

    def __init__(self, *, conflict: bool = False) -> None:
        super().__init__()
        self.conflict = conflict

    @contextlib.asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield
        if self.conflict:
            raise IntegrityError("INSERT INTO ai_batch_runs", {}, Exception("duplicate key"))


async def test_create_commits_the_template_lock_before_slow_io(
    online: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 读上线版本时锁模板行；取系统码表、写快照之前就提交，事务不跨几分钟的 I/O（会撞空闲事务超时）。
    session = FakeSession()
    locks: list[bool] = []
    commits_at_fetch: list[int] = []

    async def get(_session: Any, _prompt_id: str, *, lock: bool = False) -> Any:
        locks.append(lock)
        return template(content="草稿", release_id=RELEASE_ID)

    async def fetch(_name: str) -> str:
        commits_at_fetch.append(session.commits)
        return "政策类型名称\n信息化建设类"

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(releases, "fetch_code_table", fetch)
    await pipeline_runs.create(session, ACTOR, {"prompt_id": PROMPT_ID, "rows": [{"源ID": "p1", "政策标题": "甲"}]})  # type: ignore[arg-type]
    assert locks == [True]
    assert commits_at_fetch == [1]
    assert len(online) == 1


async def test_unknown_run_status_raises_404_without_creating_tombstone(monkeypatch: pytest.MonkeyPatch) -> None:
    """只读状态查询绝不创建已取消墓碑：建任务正在写快照时页面轮询查不到应返回 404，不能误杀在途批次。"""

    async def missing(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_repo, "get", missing)
    monkeypatch.setattr(batch_runs, "reconcile_stale", noop)
    session = _NestedSession()
    with pytest.raises(NotFoundError):
        await pipeline_runs.status(session, RUN_ID)  # type: ignore[arg-type]
    assert session.added == []


async def test_unknown_run_stop_creates_a_cancelled_tombstone(monkeypatch: pytest.MonkeyPatch) -> None:
    # 政策服务建任务超时后叫停：这边行还没插进去。只有 stop() 占位成已取消，迟到的建任务撞主键、按幂等返回已取消。
    async def missing(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_repo, "get", missing)
    session = _NestedSession()
    data = await pipeline_runs.stop(session, ACTOR, RUN_ID)  # type: ignore[arg-type]
    assert data["id"] == RUN_ID and data["status"] == "cancelled"
    [tombstone] = session.added
    assert (tombstone.source, tombstone.status, tombstone.error_message) == (
        "pipeline",
        "cancelled",
        pipeline_runs.TOMBSTONE_NOTE,
    )


async def test_tombstone_losing_the_race_stops_the_real_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # 建任务刚好先插进去：stop() 占位撞主键作罢，转而照常停止那条真任务。
    async def missing(*_args: Any, **_kwargs: Any) -> None:
        return None

    stopped: list[str] = []

    async def fake_stop(_session: Any, _caller: Any, _access: Any, run_id: str) -> dict[str, Any]:
        stopped.append(run_id)
        return {"id": run_id, "status": "cancelled"}

    monkeypatch.setattr(run_repo, "get", missing)
    monkeypatch.setattr(batch_runs, "stop_run", fake_stop)
    data = await pipeline_runs.stop(_NestedSession(conflict=True), ACTOR, RUN_ID)  # type: ignore[arg-type]
    assert data["status"] == "cancelled" and stopped == [RUN_ID]


async def test_tombstone_rejects_malformed_ids() -> None:
    with pytest.raises(NotFoundError):
        await pipeline_runs._tombstone(_NestedSession(), "../x", ACTOR)  # type: ignore[arg-type]


async def test_online_templates_batches_release_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    r1_id, r2_id = "1" * 32, "2" * 32
    t1 = template(id="a" * 32, release_id=r1_id)
    t2 = template(id="b" * 32, release_id=r2_id)
    calls: list[list[str]] = []

    async def fake_online(_session: Any, _category: str) -> list[Any]:
        return [t1, t2]

    async def fake_by_ids(_session: Any, ids: list[str]) -> dict[str, TemplateRelease]:
        calls.append(list(ids))
        return {
            r1_id: _release(id=r1_id, prompt_id=t1.id, title="模板一"),
            r2_id: _release(id=r2_id, prompt_id=t2.id, title="模板二"),
        }

    monkeypatch.setattr(prompts, "online", fake_online)
    monkeypatch.setattr(release_repo, "by_ids", fake_by_ids)
    items = await pipeline_runs.online_templates(FakeSession(), "policy")  # type: ignore[arg-type]
    assert [item["title"] for item in items] == ["模板一", "模板二"]
    assert calls == [[r1_id, r2_id]]


async def test_list_runs_offloads_page_fs_checks_in_single_thread_call(monkeypatch: pytest.MonkeyPatch) -> None:
    import anyio

    from app.domain.categories import FULL_ACCESS

    rows = [run(id="1" * 32, status="done"), run(id="2" * 32, status="done")]

    async def fake_page(*_args: Any, **_kwargs: Any) -> tuple[list[Any], int]:
        return rows, 2

    async def fake_worker_status(_session: Any) -> dict[str, bool]:
        return {"online": True}

    thread_calls: list[Any] = []
    real_run_sync = anyio.to_thread.run_sync

    async def tracked_run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
        thread_calls.append(func)
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(batch_runs, "reconcile_stale", noop)
    monkeypatch.setattr(batch_runs.repo, "page", fake_page)
    monkeypatch.setattr(batch_runs, "worker_status", fake_worker_status)
    monkeypatch.setattr(batch_runs.anyio.to_thread, "run_sync", tracked_run_sync)

    result = await batch_runs.list_runs(FakeSession(), FULL_ACCESS, page=1, page_size=20)  # type: ignore[arg-type]
    assert len(result["items"]) == 2
    assert thread_calls == [batch_runs._runs_fs_state]
