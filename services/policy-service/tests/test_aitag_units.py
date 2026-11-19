"""政策 AI 打标里不碰数据库的部分：按天读源库、内部调用、编排里的失败和中断收尾、设置校验。整批写库在集成测试里。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError, DependencyUnavailableError, VersionConflictError

from app.aitag.application import pipeline, settings, tagging
from app.aitag.domain import rules
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.errors import UserFacingError
from app.core.config import get_settings

DAY = date(2026, 10, 1)
ACTOR = Actor(id="u1", name="管理员")


class FakeCursor:
    """按 (采集日, 起始ID, 条数) 从内存数据里取，模拟源库的分页查询。"""

    def __init__(self, data: dict[date, list[str]], provinces: dict[str, str] | None = None) -> None:
        self.data = data
        self.provinces = provinces or {}
        self.queries: list[tuple[Any, ...]] = []
        self.sql: list[str] = []
        self.result: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any) -> None:
        self.queries.append(tuple(params))
        self.sql.append(sql)
        if "csys_policy_info_content" in sql:
            self.result = [{"content_id": cid, "content": f"{cid}正文"} for cid in params]
            return
        day, after, *picked, limit = params
        ids = [
            cid for cid in self.data.get(day, []) if cid > after and (not picked or self.provinces.get(cid) in picked)
        ]
        ids = ids[:limit]
        self.result = [{"content_id": cid, "collect_date": day} for cid in ids]

    def fetchall(self) -> list[dict[str, Any]]:
        return self.result

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _connect(cursor: FakeCursor) -> Any:
    connection = SimpleNamespace(cursor=lambda: cursor)
    connection.__enter__ = lambda *_: connection  # type: ignore[attr-defined]
    connection.__exit__ = lambda *_: None  # type: ignore[attr-defined]

    class Ctx:
        def __enter__(self) -> Any:
            return connection

        def __exit__(self, *_: object) -> None:
            return None

    return lambda _db: Ctx()


def test_read_batch_walks_days_and_pages_within_a_day(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.common import policy_source

    cursor = FakeCursor({DAY: ["a", "b", "c"], DAY + timedelta(2): ["d", "e"]})
    monkeypatch.setattr(policy_source, "mysql_connect", _connect(cursor))
    rows = source.read_batch(DAY, "a", 3, DAY + timedelta(5))
    # 当天从 a 之后读 b、c 不够 3 条，跳过空的第二天，第三天补 d。
    assert [row["content_id"] for row in rows] == ["b", "c", "d"]
    assert [query[:2] for query in cursor.queries] == [(DAY, "a"), (DAY + timedelta(1), ""), (DAY + timedelta(2), "")]
    assert source.read_batch(DAY + timedelta(3), "", 5, DAY + timedelta(3)) == []


def test_read_batch_reads_only_the_picked_provinces(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.common import policy_source

    cursor = FakeCursor({DAY: ["a", "b", "c", "d"]}, {"a": "北京市", "b": "河北省", "c": "北京市", "d": "天津市"})
    monkeypatch.setattr(policy_source, "mysql_connect", _connect(cursor))
    rows = source.read_batch(DAY, "", 5, DAY, ["北京市", "天津市"])
    assert [row["content_id"] for row in rows] == ["a", "c", "d"]
    # 省份作为参数绑进 IN，条数仍在最后；不选省份时 SQL 不带省份条件。
    assert cursor.queries[0] == (DAY, "", "北京市", "天津市", 5)
    assert "prov_name IN (%s, %s)" in cursor.sql[0]
    source.read_batch(DAY, "", 5, DAY)
    assert "prov_name" not in cursor.sql[-1].split("WHERE")[1]


def test_read_contents_goes_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.common import policy_source

    cursor = FakeCursor({})
    monkeypatch.setattr(policy_source, "mysql_connect", _connect(cursor))
    ids = [f"id{index:03d}" for index in range(450)]
    contents = source.read_contents(ids)
    assert len(contents) == 450 and contents["id449"] == "id449正文"
    assert [len(query) for query in cursor.queries] == [200, 200, 50]


async def test_internal_client_distinguishes_rejection_from_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_service_secret", "")
    with pytest.raises(DependencyUnavailableError, match="未配置"):
        await internal_clients.ai("GET", "/internal/v1/x")

    replies = iter(
        [
            httpx.Response(200, json={"code": "OK", "data": {"id": "r1"}}),
            httpx.Response(422, json={"code": "VALIDATION_ERROR", "message": "模板还没有上线"}),
            httpx.Response(500, json={"code": "ERR", "message": "boom"}),
        ]
    )
    real = httpx.AsyncClient
    callers: list[str] = []

    def reply(request: httpx.Request) -> httpx.Response:
        callers.append(request.headers["x-internal-service"])
        return next(replies)

    monkeypatch.setattr(get_settings(), "ai_service_secret", "s")
    # worker 进程的服务名是 policy-worker，对方只认 policy-service。
    monkeypatch.setattr(get_settings(), "service_name", "policy-worker")
    monkeypatch.setattr(
        internal_clients.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(reply), **kw)
    )
    assert await internal_clients.ai("POST", "/internal/v1/pipeline-runs") == {"id": "r1"}
    with pytest.raises(ApiError, match="还没有上线"):
        await internal_clients.ai("POST", "/internal/v1/pipeline-runs")
    with pytest.raises(DependencyUnavailableError, match="500"):
        await internal_clients.ai("GET", "/internal/v1/pipeline-runs/r1")
    assert set(callers) == {"policy-service"}


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def run_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """打标批次存在内存里；_update、abandon 都通过 repo.get_run 找到它。"""

    store: dict[str, Any] = {}
    session = FakeSession()

    async def get_run(_session: Any, run_id: uuid.UUID) -> Any:
        return store.get(str(run_id))

    async def run_of_ai_task(_session: Any, run_field: str, ai_run_id: str) -> Any:
        return next((run for run in store.values() if getattr(run, run_field, "") == ai_run_id), None)

    original_add = session.add

    def add(item: Any) -> None:
        original_add(item)
        store[str(item.id)] = item

    session.add = add  # type: ignore[method-assign]
    monkeypatch.setattr(tagging, "SessionLocal", lambda: session)
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: session)
    monkeypatch.setattr(repo, "get_run", get_run)
    monkeypatch.setattr(repo, "run_of_ai_task", run_of_ai_task)
    return store


def _config(**overrides: Any) -> Any:
    values = {
        "code": "type",
        "prompt_id": "p" * 32,
        "batch_size": 10,
        "content_max_chars": 1000,
        "daily_cost_limit": Decimal(10),
        "cursor_date": DAY,
        "cursor_content_id": "",
        "provinces": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _use_config(monkeypatch: pytest.MonkeyPatch, config: Any, spent: Decimal = Decimal(0)) -> None:
    async def get_config(*_: Any, **__: Any) -> Any:
        return config

    async def spent_since(*_: Any) -> Decimal:
        return spent

    async def no_queue(*_: Any) -> list[str]:
        return []

    monkeypatch.setattr(repo, "task", get_config)
    monkeypatch.setattr(repo, "spent_since", spent_since)
    monkeypatch.setattr(tagging.retag, "type_queue", no_queue)


async def test_missing_template_fails_with_a_message_the_page_can_show(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config(prompt_id=""))
    run_id = uuid.uuid4()
    with pytest.raises(UserFacingError, match="「政策解读」用的上线模板"):
        await tagging.run_batch(run_id, "interpret")
    run = run_store[str(run_id)]
    assert (run.task, run.status) == ("interpret", "failed") and "上线模板" in run.error_message


async def test_a_task_over_its_daily_budget_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config(daily_cost_limit=Decimal(1)), spent=Decimal("1.2"))
    run_id = uuid.uuid4()
    await tagging.run_batch(run_id, "type")
    run = run_store[str(run_id)]
    assert run.status == "success" and run.note == "今日已花 1.20 元，达到每日上限 1.00 元，留到明天"


async def test_empty_source_is_a_successful_batch(monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]) -> None:
    _use_config(monkeypatch, _config())
    monkeypatch.setattr(source, "read_batch", lambda *_: [])
    run_id = uuid.uuid4()
    await tagging.run_batch(run_id, "type")
    assert (run_store[str(run_id)].status, run_store[str(run_id)].note) == ("success", "没有新的源政策")
    # 选了省份的，说明里写明只读了哪些省份，看执行记录就知道为什么读不到。
    _use_config(monkeypatch, _config(provinces=["北京市", "河北省"]))
    scoped = uuid.uuid4()
    await tagging.run_batch(scoped, "type")
    assert run_store[str(scoped)].note == "没有新的源政策（只读 北京市、河北省）"


async def test_unexpected_errors_hide_details_from_the_page(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config())

    def broken(*_: Any) -> list[Any]:
        raise RuntimeError("mysql://user:secret@host")

    monkeypatch.setattr(source, "read_batch", broken)
    run_id = uuid.uuid4()
    with pytest.raises(RuntimeError):
        await tagging.run_batch(run_id, "type")
    assert run_store[str(run_id)].error_message == "执行失败（RuntimeError）"


async def test_ai_service_rejections_are_explained_and_outages_stay_retryable(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config())
    monkeypatch.setattr(source, "read_batch", lambda *_: [{"content_id": "c1", "collect_date": DAY}])
    monkeypatch.setattr(source, "read_contents", lambda ids: {})

    async def names(*_: Any, **__: Any) -> dict[str, str]:
        return {"text": "政策类型名称\n信息化建设类"}

    async def rejected(*_: Any, **__: Any) -> Any:
        raise ApiError("模板还没有上线", http_status=422)

    monkeypatch.setattr(internal_clients, "codebook", names)
    monkeypatch.setattr(internal_clients, "ai", rejected)
    run_id = uuid.uuid4()
    with pytest.raises(UserFacingError, match="AI 服务拒绝执行：模板还没有上线"):
        await tagging.run_batch(run_id, "type")
    assert run_store[str(run_id)].error_message == "AI 服务拒绝执行：模板还没有上线"

    async def down(*_: Any, **__: Any) -> Any:
        raise DependencyUnavailableError("ai-service 暂时不可用")

    monkeypatch.setattr(internal_clients, "ai", down)
    with pytest.raises(DependencyUnavailableError):
        await tagging.run_batch(uuid.uuid4(), "type")


async def test_cancelled_wait_stops_the_ai_run(monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]) -> None:
    """调度超时会取消这一批：ai-service 那边的任务要一起停，不然它在后台继续花钱。"""

    _use_config(monkeypatch, _config())
    monkeypatch.setattr(source, "read_batch", lambda *_: [{"content_id": "c1", "collect_date": DAY}])
    monkeypatch.setattr(source, "read_contents", lambda ids: {})
    calls: list[tuple[str, str]] = []

    async def ai(method: str, path: str, **_: Any) -> Any:
        calls.append((method, path))
        if method == "POST" and path.endswith("pipeline-runs"):
            return {"id": "r" * 32}
        if path.endswith("/stop"):
            return {}
        raise asyncio.CancelledError

    async def names(*_: Any, **__: Any) -> dict[str, str]:
        return {"text": "政策类型名称\n信息化建设类"}

    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(internal_clients, "codebook", names)
    with pytest.raises(asyncio.CancelledError):
        await tagging.run_batch(uuid.uuid4(), "type")
    assert ("POST", f"/internal/v1/pipeline-runs/{'r' * 32}/stop") in calls


async def test_abandon_marks_failed_and_stops_the_ai_run(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    run_id = uuid.uuid4()
    run_store[str(run_id)] = SimpleNamespace(
        status="running",
        stage="typing",
        cost=Decimal(0),
        type_cost=Decimal(0),
        interpret_cost=Decimal(0),
        opportunity_cost=Decimal(0),
        scenario_cost=Decimal(0),
        enrich_cost=Decimal(0),
        enrich_run_id="",
        scenario_run_id="",
        type_run_id="r" * 32,
        interpret_run_id="i" * 32,
        opportunity_run_id="",
        error_message="",
        finished_at=None,
    )
    stopped: list[str] = []

    async def ai(method: str, path: str, **_: Any) -> Any:
        stopped.append(path)
        return {}

    monkeypatch.setattr(internal_clients, "ai", ai)
    await tagging.abandon(run_id, "执行进程中断")
    # 三步里发起过的任务都要停；没发起的（空 ID）跳过。
    assert run_store[str(run_id)].status == "failed"
    assert stopped == [f"/internal/v1/pipeline-runs/{'r' * 32}/stop", f"/internal/v1/pipeline-runs/{'i' * 32}/stop"]
    await tagging.abandon(uuid.uuid4(), "不存在的批次不报错")


def _task(code: str = "type", **overrides: Any) -> Any:
    values = {
        "code": code,
        "prompt_id": "",
        "batch_size": 1000,
        "content_max_chars": 15000,
        "daily_cost_limit": Decimal(100),
        "cursor_date": DAY if code == "type" else None,
        "cursor_content_id": "c9" if code == "type" else "",
        "provinces": [],
        "version": 3,
        "updated_at": None,
        "updated_by_name": "",
    }
    return SimpleNamespace(**(values | overrides))


async def test_settings_validate_ranges_and_reset_the_cursor_on_date_change(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    events: list[dict[str, Any]] = []

    async def get_task(*_: Any, **__: Any) -> Any:
        return task

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(repo, "task", get_task)
    monkeypatch.setattr(settings, "enqueue_event", record)
    monkeypatch.setattr(settings, "today", lambda: DAY + timedelta(days=30))

    async def online() -> list[dict[str, Any]]:
        good = {
            "prompt_id": "t" * 32,
            "title": "类型判断",
            "variables": ["政策正文"],
            "output_fields": ["政策类型名称"],
        }
        return [
            settings._with_checks(good),
            settings._with_checks({**good, "prompt_id": "x" * 32, "output_fields": []}),
        ]

    monkeypatch.setattr(settings, "_online_templates", online)
    body = {"batch_size": 50, "content_max_chars": 8000, "daily_cost_limit": "20", "cursor_date": DAY.isoformat()}
    update = settings.update_task
    with pytest.raises(VersionConflictError):
        await update(FakeSession(), ACTOR, "type", {**body, "version": 1})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="每批条数"):
        await update(FakeSession(), ACTOR, "type", {**body, "batch_size": 0, "version": 3})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="晚于今天"):
        await update(FakeSession(), ACTOR, "type", {**body, "cursor_date": "2099-01-01", "version": 3})  # type: ignore[arg-type]
    kept = await update(FakeSession(), ACTOR, "type", {**body, "prompt_id": "t" * 32, "version": 3})  # type: ignore[arg-type]
    assert (kept["batch_size"], kept["cursor_content_id"], kept["version"]) == (50, "c9", 4)
    assert events[-1]["target_id"] == "policy_ai_type"
    assert events[-1]["changes"]["batch_size"] == {"from": 1000, "to": 50}
    moved = await update(FakeSession(), ACTOR, "type", {**body, "cursor_date": "2026-09-01", "version": 4})  # type: ignore[arg-type]
    assert (moved["cursor_date"], moved["cursor_content_id"]) == ("2026-09-01", "")
    # 换成放进类型判断写不回表的模板：拦下并说清楚；不存在的模板也拦下。
    with pytest.raises(ApiError, match="不能用于政策类型判断：输出字段缺少：政策类型名称"):
        await update(FakeSession(), ACTOR, "type", {**body, "prompt_id": "x" * 32, "version": 5})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="不存在、不是政策类或已下线"):
        await update(FakeSession(), ACTOR, "type", {**body, "prompt_id": "n" * 32, "version": 5})  # type: ignore[arg-type]
    full = await update(FakeSession(), ACTOR, "type", {**body, "content_max_chars": 0, "version": 5})  # type: ignore[arg-type]
    assert full["content_max_chars"] == 0  # 0 = 全文照传
    with pytest.raises(ApiError, match="正文截取字数"):
        await update(FakeSession(), ACTOR, "type", {**body, "content_max_chars": 100, "version": 6})  # type: ignore[arg-type]
    # 采集省份：去空白、去重；改省份不动读取进度（要补以前的日期就把起始日期往前调）。
    picked = {**body, "cursor_date": "2026-09-01", "provinces": [" 北京市", "北京市", "", "河北省"], "version": 6}
    scoped = await update(FakeSession(), ACTOR, "type", picked)  # type: ignore[arg-type]
    assert (scoped["provinces"], scoped["cursor_date"], scoped["cursor_content_id"]) == (
        ["北京市", "河北省"],
        "2026-09-01",
        "",
    )
    assert events[-1]["changes"]["provinces"] == {"from": [], "to": ["北京市", "河北省"]}
    with pytest.raises(ApiError, match="最多选 50 个"):
        many = {**body, "provinces": [f"省{index}" for index in range(51)], "version": 7}
        await update(FakeSession(), ACTOR, "type", many)  # type: ignore[arg-type]


async def test_only_the_type_task_has_a_reading_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task("interpret")

    async def get_task(*_: Any, **__: Any) -> Any:
        return task

    async def record(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "task", get_task)
    monkeypatch.setattr(settings, "enqueue_event", record)
    body = {"batch_size": 5, "content_max_chars": 0, "daily_cost_limit": "3.5", "cursor_date": "2026-09-01"}
    out = await settings.update_task(FakeSession(), ACTOR, "interpret", {**body, "version": 3})  # type: ignore[arg-type]
    assert (out["name"], out["job_code"], out["cursor_date"], out["daily_cost_limit"]) == (
        "政策解读",
        "policy_ai_interpret",
        "",
        "3.5",
    )


async def test_task_list_still_shows_progress_when_ai_service_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def tasks(*_: Any) -> dict[str, Any]:
        return {code: _task(code) for code in ("opportunity", "type", "interpret")}

    async def spent(_session: Any, code: str, _since: Any) -> Decimal:
        return {"type": Decimal("1.5"), "interpret": Decimal(2), "opportunity": Decimal(0), "scenario": Decimal(0)}[
            code
        ]

    async def down(*_: Any, **__: Any) -> Any:
        raise DependencyUnavailableError("ai-service 暂时不可用")

    running = SimpleNamespace(
        id=uuid.uuid4(), stage="interpreting", interpret_run_id="i" * 32, started_at=None, cost=Decimal("0.3")
    )

    async def runs(*_: Any) -> dict[str, Any]:
        return {"interpret": running}

    monkeypatch.setattr(repo, "tasks", tasks)
    monkeypatch.setattr(repo, "spent_since", spent)
    monkeypatch.setattr(repo, "running_runs", runs)

    async def pending(*_: Any) -> dict[str, int]:
        return {"type": 0, "interpret": 5, "opportunity": 2}

    monkeypatch.setattr(repo, "pending_counts", pending)
    monkeypatch.setattr(internal_clients, "ai", down)
    items = (await settings.list_tasks(FakeSession()))["items"]  # type: ignore[arg-type]
    # 按页面顺序；ai-service 不可用时进度取不到，但正在做什么照样显示。
    assert [item["code"] for item in items] == ["type", "interpret", "opportunity"]
    assert [item["spent_today"] for item in items] == ["1.5", "2", "0"]
    assert [item["pending"] for item in items] == [0, 5, 2]
    assert items[0]["current"] is None
    assert (items[1]["current"]["stage_name"], items[1]["current"]["done"]) == ("模型解读中", None)
    templates = await settings.templates()
    assert templates["items"] == [] and "不可用" in templates["error"]


async def test_running_batch_shows_how_far_the_ai_run_has_got(monkeypatch: pytest.MonkeyPatch) -> None:
    running = SimpleNamespace(id=uuid.uuid4(), stage="typing", type_run_id="t" * 32, started_at=None, cost=Decimal(0))

    async def ai(method: str, path: str, **_: Any) -> Any:
        assert path.endswith("t" * 32)
        return {"done_count": 40, "total_count": 100}

    monkeypatch.setattr(internal_clients, "ai", ai)
    data = await settings._current(running)  # type: ignore[arg-type]
    assert data is not None and (data["stage_name"], data["done"], data["total"]) == ("模型判断中", 40, 100)
    assert await settings._current(None) is None


async def test_each_stage_records_its_own_cost(monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]) -> None:
    run_id = uuid.uuid4()
    run_store[str(run_id)] = SimpleNamespace(cost=Decimal(0), interpret_run_id="", interpret_cost=Decimal(0))

    async def ai(method: str, path: str, **_: Any) -> Any:
        if method == "POST":
            return {"id": "r" * 32}
        if path.endswith("/results"):
            return {"items": []}
        return {"status": "done", "inference_cost": "0.4", "search_cost": "0.1"}

    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0), run=Decimal("0.2"))
    await pipeline.ask(run_id, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")
    stored = run_store[str(run_id)]
    assert (stored.interpret_cost, stored.cost, spend.run) == (Decimal("0.5"), Decimal("0.7"), Decimal("0.7"))


async def test_type_step_reads_only_through_the_day_before_yesterday(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """源政策 ID 是哈希、不按入库先后排，读过一天后再入库的会漏；源库每个采集日的数据第二天才入库完
    （实测最晚到第二天晚上），所以只读到前天整天。"""

    _use_config(monkeypatch, _config(cursor_date=None))
    windows: list[tuple[Any, ...]] = []
    monkeypatch.setattr(source, "read_batch", lambda *args: windows.append(args) or [])
    await tagging.run_batch(uuid.uuid4(), "type")
    until = tagging.today() - timedelta(days=2)
    assert windows == [(until, "", 10, until, [])]


async def test_rereading_days_skips_policies_already_tagged(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """读取进度往回调、重扫几天补漏时，已经打好标的不能再问一遍模型；全都打过就只把进度往前挪。"""

    config = _config()
    _use_config(monkeypatch, config)
    rows = [{"content_id": f"c{index}", "collect_date": DAY} for index in range(3)]
    monkeypatch.setattr(source, "read_batch", lambda *_: rows)

    async def all_tagged(_session: Any, ids: list[str]) -> set[str]:
        return set(ids)

    monkeypatch.setattr(repo, "tagged_source_ids", all_tagged)
    asked: list[Any] = []

    async def ai(*args: Any, **_: Any) -> Any:
        asked.append(args)
        return {}

    monkeypatch.setattr(internal_clients, "ai", ai)
    run_id = uuid.uuid4()
    await tagging.run_batch(run_id, "type")
    assert asked == []
    assert (config.cursor_date, config.cursor_content_id) == (DAY, "c2")
    assert "都已经打过类型标" in run_store[str(run_id)].note


@pytest.mark.real_template_check
async def test_a_template_that_lost_its_required_field_stops_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一模板重新上线去掉了「政策类型名称」：每批开始前复核，不然每条都记成没判断出类型、进度照常前移。"""

    async def ai(*_: Any, **__: Any) -> Any:
        return [
            {
                "prompt_id": "p",
                "title": "类型判断",
                "release_no": 3,
                "variables": ["政策正文"],
                "output_fields": ["理由"],
            }
        ]

    monkeypatch.setattr(internal_clients, "ai", ai)
    with pytest.raises(UserFacingError, match="第 3 版不能用于"):
        await tagging.check_template_now("type", "p")
    with pytest.raises(UserFacingError, match="已下线"):
        await tagging.check_template_now("type", "gone")


async def test_retag_keeps_manual_edits_and_does_not_duplicate_another_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """重打后内容和另一条一样（原来只差一句失败备注）：不写、出队、备注注明，整批不能因撞唯一约束回滚；
    人填了穿透词的那条重打后穿透词还在。"""

    from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

    def tag(content_id: str, remark: str, **manual: str) -> BaseTag:
        values = rules.base_tag_values({"name": "政策甲"}, ["信息化建设类"] if not remark else [], remark) | manual
        row = BaseTag(source_content_id=content_id, version=1, **values)
        row.content_hash = content_hash(values, BASE_TAG_FIELDS)
        row.type_retag_at = datetime.now(UTC)
        return row

    done = tag("c0", "")
    failed = tag("c1", "AI 类型判断失败：限流")
    manual = tag("c2", "AI 类型判断失败：限流；领导关注", is_penetrate="是", penetrate_words="数字政府")
    rows_by_hash = {row.content_hash: row for row in (done, failed, manual)}

    async def by_source(_session: Any, _ids: list[str]) -> dict[str, BaseTag]:
        return {"c1": failed, "c2": manual}

    async def by_hash(_session: Any, digest: str) -> BaseTag | None:
        return rows_by_hash.get(digest)

    async def task(_session: Any, _code: str, lock: bool = False) -> Any:
        return SimpleNamespace(cursor_date=DAY, cursor_content_id="")

    async def noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "base_tags_by_source", by_source)
    monkeypatch.setattr(repo, "base_tag_by_hash", by_hash)
    monkeypatch.setattr(repo, "task", task)
    monkeypatch.setattr(tagging, "enqueue_event", noop)
    monkeypatch.setattr(tagging, "SessionLocal", FakeSession)
    rows = [
        {"content_id": "c1", "name": "政策甲", "collect_date": DAY},
        {"content_id": "c2", "name": "政策甲", "collect_date": DAY},
    ]
    ok = {"error": "", "items": [{"政策类型名称": "信息化建设类"}]}
    counts = await tagging._save_types(uuid.uuid4(), rows, [ok, ok], ["信息化建设类"], retag=True)

    assert counts == {"processed": 2, "tagged": 1, "failed": 0, "duplicate": 1}
    assert failed.type_retag_at is None and failed.policy_types == ""
    assert failed.remark == f"{rules.DUPLICATE_NOTE}（源政策ID c1）"
    assert manual.type_retag_at is None and manual.policy_types == "信息化建设类"
    assert (manual.is_penetrate, manual.penetrate_words, manual.remark) == ("是", "数字政府", "领导关注")


async def test_retag_of_several_copies_of_one_page_does_not_collide(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一网页采了三条：甲成功，乙、丙失败原因不同。一起重判后乙、丙都和甲相同，
    两条的备注要各不相同，否则彼此撞内容哈希、整批回滚，队列清不掉、每次执行都先花钱再失败。"""

    from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

    def tag(content_id: str, remark: str) -> BaseTag:
        values = rules.base_tag_values({"name": "政策甲"}, ["信息化建设类"] if not remark else [], remark)
        row = BaseTag(source_content_id=content_id, version=1, **values)
        row.content_hash = content_hash(values, BASE_TAG_FIELDS)
        return row

    done = tag("c0", "")
    second, third = tag("c1", "AI 类型判断失败：限流"), tag("c2", "AI 类型判断失败：超时")

    async def by_source(_session: Any, _ids: list[str]) -> dict[str, BaseTag]:
        return {"c1": second, "c2": third}

    async def by_hash(_session: Any, digest: str) -> BaseTag | None:
        return {row.content_hash: row for row in (done, second, third)}.get(digest)

    async def task(_session: Any, _code: str, lock: bool = False) -> Any:
        return SimpleNamespace(cursor_date=DAY, cursor_content_id="")

    async def noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "base_tags_by_source", by_source)
    monkeypatch.setattr(repo, "base_tag_by_hash", by_hash)
    monkeypatch.setattr(repo, "task", task)
    monkeypatch.setattr(tagging, "enqueue_event", noop)
    monkeypatch.setattr(tagging, "SessionLocal", FakeSession)
    rows = [{"content_id": cid, "name": "政策甲", "collect_date": DAY} for cid in ("c1", "c2")]
    ok = {"error": "", "items": [{"政策类型名称": "信息化建设类"}]}
    counts = await tagging._save_types(uuid.uuid4(), rows, [ok, ok], ["信息化建设类"], retag=True)
    assert counts["duplicate"] == 2
    assert len({done.content_hash, second.content_hash, third.content_hash}) == 3


async def test_abandon_books_the_interrupted_stage_cost(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """中断时那一步的花费只在 cost 里：收尾要补到步骤费用列，当日上限按步骤列算才不会漏掉这笔钱。"""

    async def quiet(_ai_run_id: str) -> None:
        return None

    monkeypatch.setattr(tagging, "stop_quietly", quiet)
    run_id = uuid.uuid4()
    run = SimpleNamespace(
        id=run_id,
        status="running",
        stage="interpreting",
        cost=Decimal("3"),
        type_cost=Decimal("1"),
        interpret_cost=Decimal(0),
        opportunity_cost=Decimal(0),
        scenario_cost=Decimal(0),
        enrich_cost=Decimal(0),
        enrich_run_id="",
        scenario_run_id="",
        type_run_id="a",
        interpret_run_id="b",
        opportunity_run_id=None,
    )
    run_store[str(run_id)] = run
    await tagging.abandon(run_id, "进程中断")
    assert (run.status, run.interpret_cost, run.type_cost) == ("failed", Decimal("2"), Decimal("1"))


def _run_row(**values: Any) -> SimpleNamespace:
    base = {
        "status": "running",
        "stage": "interpreting",
        "cost": Decimal(0),
        "type_cost": Decimal(0),
        "interpret_cost": Decimal(0),
        "opportunity_cost": Decimal(0),
        "scenario_cost": Decimal(0),
        "enrich_cost": Decimal(0),
        "enrich_run_id": "",
        "type_run_id": "",
        "interpret_run_id": "",
        "opportunity_run_id": "",
        "scenario_run_id": "",
        "error_message": "",
        "finished_at": None,
    }
    return SimpleNamespace(**(base | values))


async def test_a_few_missed_polls_do_not_fail_the_batch(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """等一两个小时里 ai-service 重建一次很平常：问不到就再等等，不能为一次没问到让整批失败、下批再花一遍钱。"""

    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()
    polls: list[int] = []

    async def ai(method: str, path: str, **_: Any) -> Any:
        if method == "POST":
            return {"id": "r" * 32, "reused": 0}
        if path.endswith("/results"):
            return {"items": []}
        polls.append(1)
        if len(polls) < 3:
            raise DependencyUnavailableError("ai-service 暂时不可用")
        return {"status": "done", "done_count": 1, "inference_cost": "0.3"}

    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    status, _ = await pipeline.ask(run_id, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")
    assert status["status"] == "done" and len(polls) == 3


async def test_giving_up_on_the_ai_run_stops_it_and_books_what_it_spent(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """一直问不到：先叫停 ai-service 那边，批次记失败时把已花的钱记到步骤费用列，重试时当日额度才算得到这笔钱。"""

    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()
    calls: list[tuple[str, str]] = []

    async def ai(method: str, path: str, **_: Any) -> Any:
        calls.append((method, path))
        if method == "POST" and path.endswith("pipeline-runs"):
            return {"id": "r" * 32}
        if path.endswith("/stop"):
            return {}
        if len(calls) == 2:
            return {"status": "running", "inference_cost": "1.5"}
        raise DependencyUnavailableError("ai-service 暂时不可用")

    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    monkeypatch.setattr(pipeline, "POLL_MISSES", 2)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    with pytest.raises(DependencyUnavailableError):
        await pipeline.ask(run_id, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")
    assert ("POST", f"/internal/v1/pipeline-runs/{'r' * 32}/stop") in calls
    await tagging._fail(run_id, "执行失败")
    stored = run_store[str(run_id)]
    assert (stored.status, stored.interpret_cost) == ("failed", Decimal("1.5"))


async def test_ask_persists_client_run_id_and_stops_on_create_timeout(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def ai(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path, kwargs.get("json")))
        if method == "POST" and path == "/internal/v1/pipeline-runs":
            raise DependencyUnavailableError("create timeout")
        return {}

    monkeypatch.setattr(internal_clients, "ai", ai)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    with pytest.raises(DependencyUnavailableError):
        await pipeline.ask(run_id, spend, prompt_id="p", rows=[{"源ID": "1"}], caller="c", run_field="type_run_id")
    saved_id = run_store[str(run_id)].type_run_id
    assert len(saved_id) == 32
    assert calls[0][2] is not None and calls[0][2]["client_run_id"] == saved_id
    assert ("POST", f"/internal/v1/pipeline-runs/{saved_id}/stop", None) in calls


async def test_the_next_batch_reuses_answers_from_the_failed_one(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """上一批失败了，它在 ai-service 已答好的行这一批沿用：那批还在收尾就先叫停、等它停稳再发起。"""

    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()
    old = "o" * 32

    async def failed_ai_run(*_: Any, **__: Any) -> str:
        return old

    states = iter(["stopping", "cancelled"])
    sent: list[dict[str, Any]] = []
    calls: list[tuple[str, str]] = []

    async def ai(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path))
        if path == f"/internal/v1/pipeline-runs/{old}":
            return {"status": next(states)}
        if path.endswith("/stop"):
            return {}
        if method == "POST":
            sent.append(kwargs["json"])
            return {"id": "r" * 32, "reused": 7}
        if path.endswith("/results"):
            return {"items": []}
        return {"status": "done", "done_count": 9}

    monkeypatch.setattr(repo, "failed_ai_run", failed_ai_run)
    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    status, _ = await pipeline.ask(run_id, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")
    assert sent[0]["reuse_run_id"] == old and status["reused"] == 7
    assert ("POST", f"/internal/v1/pipeline-runs/{old}/stop") in calls


async def test_the_failed_batch_gets_its_final_cost_once_the_ai_run_settles(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """上一批失败时只补记到最后一次轮询到的花费，之后那边又花的钱今日已花里没有：停稳后按最终花费补上差额。"""

    old = "o" * 32
    failed = _run_row(interpret_run_id=old, interpret_cost=Decimal("0.4"), cost=Decimal("0.4"))
    run_store["previous"] = failed
    current = uuid.uuid4()
    run_store[str(current)] = _run_row()

    async def failed_ai_run(*_: Any, **__: Any) -> str:
        return old

    async def ai(method: str, path: str, **kwargs: Any) -> Any:
        if path == f"/internal/v1/pipeline-runs/{old}":
            return {"status": "cancelled", "inference_cost": "0.9", "search_cost": "0.1"}
        if method == "POST":
            return {"id": "r" * 32, "reused": 0}
        if path.endswith("/results"):
            return {"items": []}
        return {"status": "done", "done_count": 1}

    monkeypatch.setattr(repo, "failed_ai_run", failed_ai_run)
    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    await pipeline.ask(current, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")
    assert (failed.interpret_cost, failed.cost) == (Decimal("1.0"), Decimal("1.0"))


async def test_an_ai_run_that_never_started_fails_the_batch(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """ai-service 一行都没跑就失败（模型不认识这类）：不能把整批记成「未执行」、批次却记成功，天天如此。"""

    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()

    async def ai(method: str, path: str, **_: Any) -> Any:
        if method == "POST":
            return {"id": "r" * 32}
        return {"status": "failed", "done_count": 0, "error_message": "未知模型：x"}

    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    with pytest.raises(UserFacingError, match="未知模型"):
        await pipeline.ask(run_id, spend, prompt_id="p", rows=[], caller="c", run_field="interpret_run_id")


async def test_retag_only_redoes_interpretation_when_the_type_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """用新模板重判一千条类型没变的政策，不能把最贵的解读整批重跑；改成非信息化的，没人核对过的 AI 解读行清掉；
    这一批跑的时候有人改了起始日期，收尾也不能把它改回去。"""

    from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

    done_at = datetime(2026, 10, 1, tzinfo=UTC)

    def tag(content_id: str, types: list[str]) -> BaseTag:
        values = rules.base_tag_values({"name": f"政策{content_id}"}, types, "")
        row = BaseTag(source_content_id=content_id, version=1, interpreted_at=done_at, opportunity_at=done_at, **values)
        row.content_hash = content_hash(values, BASE_TAG_FIELDS)
        return row

    same, changed = tag("c1", ["信息化建设类"]), tag("c2", ["信息化建设类"])
    untouched_row = SimpleNamespace(data_status="待验证", tagged_at=done_at, updated_at=done_at, source_content_id="c2")
    verified_row = SimpleNamespace(
        data_status="人工验证", tagged_at=done_at, updated_at=done_at, source_content_id="c2"
    )
    deleted: list[Any] = []
    config = SimpleNamespace(cursor_date=date(2026, 9, 1), cursor_content_id="")  # 有人刚改了起始日期

    async def by_source(_session: Any, _ids: list[str]) -> dict[str, BaseTag]:
        return {"c1": same, "c2": changed}

    async def none_by_hash(*_: Any) -> None:
        return None

    async def interpretations(_session: Any, ids: list[str]) -> dict[str, list[Any]]:
        return {"c2": [untouched_row, verified_row]} if "c2" in ids else {}

    async def delete_rows(_session: Any, rows: list[Any]) -> None:
        deleted.extend(rows)

    async def task(*_: Any, **__: Any) -> Any:
        return config

    async def noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "base_tags_by_source", by_source)
    monkeypatch.setattr(repo, "base_tag_by_hash", none_by_hash)
    monkeypatch.setattr(repo, "ai_interpretations", interpretations)
    monkeypatch.setattr(repo, "delete_rows", delete_rows)
    monkeypatch.setattr(repo, "task", task)
    monkeypatch.setattr(tagging, "enqueue_event", noop)
    monkeypatch.setattr(tagging, "SessionLocal", FakeSession)
    rows = [{"content_id": cid, "name": f"政策{cid}", "collect_date": DAY} for cid in ("c1", "c2")]
    results = [
        {"error": "", "items": [{"政策类型名称": "信息化建设类"}]},
        {"error": "", "items": [{"政策类型名称": "产业发展类"}]},
    ]
    known = ["信息化建设类", "产业发展类"]
    await tagging._save_types(uuid.uuid4(), rows, results, known, retag=True, start=(DAY, ""))
    assert same.interpreted_at == done_at and same.opportunity_at == done_at
    assert changed.interpreted_at is None and changed.need_interpret == "否"
    assert deleted == [untouched_row]
    # 按天读的这一批开始时进度是（DAY, ""），收尾时已经被人改成 9-1：不能按这一批读到的位置改回去。
    await tagging._save_types(uuid.uuid4(), rows, results, known, retag=False, start=(DAY, ""))
    assert (config.cursor_date, config.cursor_content_id) == (date(2026, 9, 1), "")
    config.cursor_date = DAY
    await tagging._save_types(uuid.uuid4(), rows, results, known, retag=False, start=(DAY, ""))
    assert (config.cursor_date, config.cursor_content_id) == (DAY, "c2")


async def test_retag_keeps_interpretation_failures_and_the_old_result_when_the_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重判类型没变：上次的「解读失败」留着，这条还能在「解读失败」里筛出来重新解读。
    重判本身没问成（网络、限流）：上次判好的类型和解读都不动，只记这次失败、出队。"""

    from app.policy.domain.fields import AI_NOTE_INTERPRET_FAILED, AI_NOTE_TYPE_FAILED
    from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

    done_at = datetime(2026, 10, 1, tzinfo=UTC)
    retag_at = datetime(2026, 10, 2, tzinfo=UTC)

    def tag(content_id: str) -> BaseTag:
        values = rules.base_tag_values({"name": f"政策{content_id}"}, ["信息化建设类"], "")
        values["remark"] = f"{AI_NOTE_INTERPRET_FAILED}：超时"
        row = BaseTag(
            source_content_id=content_id,
            version=1,
            interpreted_at=done_at,
            opportunity_at=done_at,
            type_retag_at=retag_at,
            **values,
        )
        row.content_hash = content_hash(values, BASE_TAG_FIELDS)
        return row

    same, broken = tag("c1"), tag("c2")
    deleted: list[Any] = []
    config = SimpleNamespace(cursor_date=DAY, cursor_content_id="")

    async def by_source(_session: Any, _ids: list[str]) -> dict[str, BaseTag]:
        return {"c1": same, "c2": broken}

    async def none_by_hash(*_: Any) -> None:
        return None

    async def interpretations(*_: Any) -> dict[str, list[Any]]:
        return {}

    async def delete_rows(_session: Any, rows: list[Any]) -> None:
        deleted.extend(rows)

    async def task(*_: Any, **__: Any) -> Any:
        return config

    async def noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "base_tags_by_source", by_source)
    monkeypatch.setattr(repo, "base_tag_by_hash", none_by_hash)
    monkeypatch.setattr(repo, "ai_interpretations", interpretations)
    monkeypatch.setattr(repo, "delete_rows", delete_rows)
    monkeypatch.setattr(repo, "task", task)
    monkeypatch.setattr(tagging, "enqueue_event", noop)
    monkeypatch.setattr(tagging, "SessionLocal", FakeSession)
    rows = [{"content_id": cid, "name": f"政策{cid}", "collect_date": DAY} for cid in ("c1", "c2")]
    results = [{"error": "", "items": [{"政策类型名称": "信息化建设类"}]}, {"error": "请求超时", "items": []}]
    counts = await tagging._save_types(uuid.uuid4(), rows, results, ["信息化建设类"], retag=True)

    assert counts["failed"] == 1 and deleted == []
    assert same.remark == f"{AI_NOTE_INTERPRET_FAILED}：超时" and same.interpreted_at == done_at
    assert same.type_retag_at is None
    assert (broken.policy_types, broken.need_interpret, broken.interpreted_at) == ("信息化建设类", "是", done_at)
    assert broken.remark.startswith(f"{AI_NOTE_TYPE_FAILED}：请求超时（保留了上次的类型）")
    assert broken.remark.endswith(f"{AI_NOTE_INTERPRET_FAILED}：超时")
    assert broken.type_retag_at is None and broken.tagged_at == broken.updated_at


async def test_internal_json_is_sent_as_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """汉字转义成 \\uXXXX 一个字 6 字节，一批政策正文就超过 ai-service 的请求体上限。"""

    real = httpx.AsyncClient
    bodies: list[bytes] = []

    def reply(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(200, json={"code": "OK", "data": {}})

    monkeypatch.setattr(get_settings(), "ai_service_secret", "s")
    monkeypatch.setattr(
        internal_clients.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(reply), **kw)
    )
    await internal_clients.ai("POST", "/internal/v1/pipeline-runs", json={"rows": [{"政策正文": "数字政府"}]})
    assert bodies == ['{"rows": [{"政策正文": "数字政府"}]}'.encode()]


async def test_a_batch_too_large_for_ai_service_sends_what_fits_and_leaves_the_rest(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    """超出一次能发的大小的行不发，记成未执行：读取进度、待办都不前移，下一批接着做。原来整批 413，天天失败。"""

    run_id = uuid.uuid4()
    run_store[str(run_id)] = _run_row()
    sent: list[int] = []

    async def ai(method: str, path: str, **kwargs: Any) -> Any:
        if method == "POST":
            sent.append(len(kwargs["json"]["rows"]))
            return {"id": "r" * 32, "reused": 0}
        if path.endswith("/results"):
            return {"items": [{"error": "", "items": [{"政策类型名称": "信息化建设类"}]}] * sent[0]}
        return {"status": "done", "done_count": sent[0], "inference_cost": "0.3"}

    rows = [{"政策正文": "字" * 100} for _ in range(3)]
    monkeypatch.setattr(pipeline, "PIPELINE_ROWS_BUDGET", 2 * len(json.dumps(rows[0], ensure_ascii=False).encode()) + 2)
    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    spend = pipeline.Spend(limit=Decimal(10), before=Decimal(0))
    _, results = await pipeline.ask(run_id, spend, prompt_id="p", rows=rows, caller="c", run_field="type_run_id")
    assert sent == [2] and len(results) == 3
    assert [pipeline.not_run(result) for result in results] == [False, False, True]
    assert rules.resume_point(results, pipeline.NOT_RUN) == 2


async def test_new_copies_of_an_existing_policy_are_remembered_so_a_rescan_does_not_pay_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """和已有基础标签内容一样的新政策不建行；原来也不留记录，读取进度往回调重扫时又当成新的、再付一遍钱。"""

    from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

    values = rules.base_tag_values({"name": "政策甲"}, ["信息化建设类"], "")
    existing = BaseTag(source_content_id="c0", version=1, **values)
    existing.content_hash = content_hash(values, BASE_TAG_FIELDS)
    marked: list[list[str]] = []

    async def by_source(*_: Any) -> dict[str, BaseTag]:
        return {}

    async def by_hash(_session: Any, digest: str) -> BaseTag | None:
        return existing if digest == existing.content_hash else None

    async def mark(_session: Any, ids: list[str], *_: Any) -> None:
        marked.append(ids)

    async def task(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(cursor_date=DAY, cursor_content_id="")

    async def noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(repo, "base_tags_by_source", by_source)
    monkeypatch.setattr(repo, "base_tag_by_hash", by_hash)
    monkeypatch.setattr(repo, "mark_skipped", mark)
    monkeypatch.setattr(repo, "task", task)
    monkeypatch.setattr(tagging, "enqueue_event", noop)
    monkeypatch.setattr(tagging, "SessionLocal", FakeSession)
    rows = [{"content_id": "c9", "name": "政策甲", "collect_date": DAY}]
    results = [{"error": "", "items": [{"政策类型名称": "信息化建设类"}]}]
    await tagging._save_types(uuid.uuid4(), rows, results, ["信息化建设类"], retag=False)
    assert marked == [["c9"]]
