"""政策 AI 打标里不碰数据库的部分：按天读源库、内部调用、编排里的失败和中断收尾、设置校验。整批写库在集成测试里。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError, DependencyUnavailableError, VersionConflictError

from app.aitag.application import pipeline, settings, tagging
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.errors import UserFacingError
from app.core.config import get_settings

DAY = date(2026, 10, 1)
ACTOR = Actor(id="u1", name="管理员")


class FakeCursor:
    """按 (采集日, 起始ID, 条数) 从内存数据里取，模拟源库的分页查询。"""

    def __init__(self, data: dict[date, list[str]]) -> None:
        self.data = data
        self.queries: list[tuple[Any, ...]] = []
        self.result: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any) -> None:
        self.queries.append(tuple(params))
        if "csys_policy_info_content" in sql:
            self.result = [{"content_id": cid, "content": f"{cid}正文"} for cid in params]
            return
        day, after, limit = params
        ids = [cid for cid in self.data.get(day, []) if cid > after][:limit]
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
    cursor = FakeCursor({DAY: ["a", "b", "c"], DAY + timedelta(2): ["d", "e"]})
    monkeypatch.setattr(source, "mysql_connect", _connect(cursor))
    rows = source.read_batch(DAY, "a", 3, DAY + timedelta(5))
    # 当天从 a 之后读 b、c 不够 3 条，跳过空的第二天，第三天补 d。
    assert [row["content_id"] for row in rows] == ["b", "c", "d"]
    assert [query[:2] for query in cursor.queries] == [(DAY, "a"), (DAY + timedelta(1), ""), (DAY + timedelta(2), "")]
    assert source.read_batch(DAY + timedelta(3), "", 5, DAY + timedelta(3)) == []


def test_read_contents_goes_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor({})
    monkeypatch.setattr(source, "mysql_connect", _connect(cursor))
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

    original_add = session.add

    def add(item: Any) -> None:
        original_add(item)
        store[str(item.id)] = item

    session.add = add  # type: ignore[method-assign]
    monkeypatch.setattr(tagging, "SessionLocal", lambda: session)
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: session)
    monkeypatch.setattr(repo, "get_run", get_run)
    return store


def _config(**overrides: Any) -> Any:
    values = {
        "type_prompt_id": "p" * 32,
        "interpret_prompt_id": "",
        "opportunity_prompt_id": "",
        "batch_size": 10,
        "content_max_chars": 1000,
        "daily_cost_limit": Decimal(10),
        "cursor_date": DAY,
        "cursor_content_id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _use_config(monkeypatch: pytest.MonkeyPatch, config: Any, spent: Decimal = Decimal(0)) -> None:
    async def get_config(*_: Any, **__: Any) -> Any:
        return config

    async def spent_since(*_: Any) -> Decimal:
        return spent

    monkeypatch.setattr(repo, "config", get_config)
    monkeypatch.setattr(repo, "spent_since", spent_since)


async def test_missing_template_fails_with_a_message_the_page_can_show(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config(type_prompt_id=""))
    run_id = uuid.uuid4()
    with pytest.raises(UserFacingError, match="上线模板"):
        await tagging.run_batch(run_id)
    run = run_store[str(run_id)]
    assert run.status == "failed" and "上线模板" in run.error_message


async def test_empty_source_is_a_successful_batch(monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]) -> None:
    _use_config(monkeypatch, _config())
    monkeypatch.setattr(source, "read_batch", lambda *_: [])
    run_id = uuid.uuid4()
    await tagging.run_batch(run_id)
    assert (run_store[str(run_id)].status, run_store[str(run_id)].note) == ("success", "类型判断：没有新的源政策")


async def test_unexpected_errors_hide_details_from_the_page(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    _use_config(monkeypatch, _config())

    def broken(*_: Any) -> list[Any]:
        raise RuntimeError("mysql://user:secret@host")

    monkeypatch.setattr(source, "read_batch", broken)
    run_id = uuid.uuid4()
    with pytest.raises(RuntimeError):
        await tagging.run_batch(run_id)
    assert run_store[str(run_id)].error_message == "执行失败（RuntimeError）"


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
        await tagging.run_batch(uuid.uuid4())
    assert ("POST", f"/internal/v1/pipeline-runs/{'r' * 32}/stop") in calls


async def test_abandon_marks_failed_and_stops_the_ai_run(
    monkeypatch: pytest.MonkeyPatch, run_store: dict[str, Any]
) -> None:
    run_id = uuid.uuid4()
    run_store[str(run_id)] = SimpleNamespace(
        status="running",
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


def _settings_config() -> Any:
    return SimpleNamespace(
        type_prompt_id="",
        interpret_prompt_id="",
        opportunity_prompt_id="",
        batch_size=1000,
        content_max_chars=15000,
        daily_cost_limit=Decimal(100),
        cursor_date=DAY,
        cursor_content_id="c9",
        version=3,
        updated_at=None,
        updated_by_name="",
    )


async def test_settings_validate_ranges_and_reset_the_cursor_on_date_change(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _settings_config()
    events: list[dict[str, Any]] = []

    async def get_config(*_: Any, **__: Any) -> Any:
        return config

    async def record(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(repo, "config", get_config)
    monkeypatch.setattr(settings, "enqueue_event", record)
    monkeypatch.setattr(settings, "today", lambda: DAY + timedelta(days=30))
    body = {"batch_size": 50, "content_max_chars": 8000, "daily_cost_limit": "20", "cursor_date": DAY.isoformat()}
    with pytest.raises(VersionConflictError):
        await settings.update(FakeSession(), ACTOR, {**body, "version": 1})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="每批条数"):
        await settings.update(FakeSession(), ACTOR, {**body, "batch_size": 0, "version": 3})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="晚于今天"):
        await settings.update(FakeSession(), ACTOR, {**body, "cursor_date": "2099-01-01", "version": 3})  # type: ignore[arg-type]
    kept = await settings.update(FakeSession(), ACTOR, {**body, "type_prompt_id": "t" * 32, "version": 3})  # type: ignore[arg-type]
    assert (kept["batch_size"], kept["cursor_content_id"], kept["version"]) == (50, "c9", 4)
    assert events[-1]["changes"]["batch_size"] == {"from": 1000, "to": 50}
    moved = await settings.update(FakeSession(), ACTOR, {**body, "cursor_date": "2026-09-01", "version": 4})  # type: ignore[arg-type]
    assert (moved["cursor_date"], moved["cursor_content_id"]) == ("2026-09-01", "")


async def test_overview_still_shows_settings_when_ai_service_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_config(*_: Any, **__: Any) -> Any:
        return _settings_config()

    async def spent(*_: Any) -> Decimal:
        return Decimal("1.5")

    async def down(*_: Any, **__: Any) -> Any:
        raise DependencyUnavailableError("ai-service 暂时不可用")

    running = SimpleNamespace(
        id=uuid.uuid4(),
        stage="interpreting",
        interpret_run_id="i" * 32,
        started_at=None,
        cost=Decimal("0.3"),
    )

    async def current(*_: Any) -> Any:
        return running

    monkeypatch.setattr(repo, "config", get_config)
    monkeypatch.setattr(repo, "spent_since", spent)
    monkeypatch.setattr(repo, "running_run", current)
    monkeypatch.setattr(internal_clients, "ai", down)
    data = await settings.overview(FakeSession())  # type: ignore[arg-type]
    # ai-service 不可用：进度取不到，但正在跑哪一步照样显示。
    assert (data["current"]["stage_name"], data["current"]["done"]) == ("政策解读", None)
    assert data["templates"] == [] and "不可用" in data["templates_error"]
    assert (data["spent_today"], data["config"]["cursor_content_id"]) == ("1.5", "c9")


async def test_running_batch_shows_how_far_the_ai_run_has_got(monkeypatch: pytest.MonkeyPatch) -> None:
    running = SimpleNamespace(id=uuid.uuid4(), stage="typing", type_run_id="t" * 32, started_at=None, cost=Decimal(0))

    async def current(*_: Any) -> Any:
        return running

    async def ai(method: str, path: str, **_: Any) -> Any:
        assert path.endswith("t" * 32)
        return {"done_count": 40, "total_count": 100}

    monkeypatch.setattr(repo, "running_run", current)
    monkeypatch.setattr(internal_clients, "ai", ai)
    data = await settings._current(FakeSession())  # type: ignore[arg-type]
    assert data is not None and (data["stage_name"], data["done"], data["total"]) == ("类型判断", 40, 100)


async def test_billing_sums_each_day_and_the_period(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    async def daily(_session: Any, since: Any) -> list[dict[str, Any]]:
        seen.append(since)
        return [
            {
                "day": DAY,
                "runs": 2,
                "cost": Decimal("1.5"),
                "type_cost": Decimal("0.5"),
                "interpret_cost": Decimal(1),
                "opportunity_cost": None,
                "source_rows": 40,
                "tagged_rows": 38,
                "interpret_rows": 12,
            },
            {
                "day": DAY - timedelta(1),
                "runs": 1,
                "cost": Decimal("0.25"),
                "type_cost": Decimal("0.25"),
                "interpret_cost": Decimal(0),
                "opportunity_cost": Decimal(0),
                "source_rows": 10,
                "tagged_rows": 10,
                "interpret_rows": None,
            },
        ]

    monkeypatch.setattr(repo, "daily_billing", daily)
    monkeypatch.setattr(settings, "today", lambda: DAY)
    data = await settings.billing(FakeSession(), 999)  # type: ignore[arg-type]
    assert data["days"] == 366 and seen[0] == pipeline.day_start(DAY - timedelta(days=365))
    first, second = data["items"]
    assert (first["day"], first["opportunity_cost"], first["tagged_rows"], second["interpret_rows"]) == (
        "2026-10-01",
        "0",
        38,
        0,
    )
    assert data["total"] == {"cost": "1.75", "type_cost": "0.75", "interpret_cost": "1", "opportunity_cost": "0"}


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
