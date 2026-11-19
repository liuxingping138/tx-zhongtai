"""调度的页面操作与队列规则：停用取消排队、手动触发防重复、到点计划合并、领取任务。会话用脚本化替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from platform_common.errors import NotFoundError, VersionConflictError
from platform_common.scheduler import (
    LONG_LANE,
    SHORT_LANE,
    Job,
    JobUpdate,
    Scheduler,
    claim_failure,
    fail_run,
    next_daily,
)

from .scheduler_tables import RunRow as _RunRow
from .scheduler_tables import tables

NOW = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)
ACTOR = SimpleNamespace(id="u1", name="管理员")


async def _noop(_batch: uuid.UUID) -> None:
    return None


def _scheduler(**jobs: Job) -> Scheduler:
    registered = list(jobs.values()) or [Job("crawler", "爬虫监测增量同步", _noop), Job("other", "其他", _noop)]
    return Scheduler(jobs=registered, **tables(), audit=AsyncMock())


def _job(**overrides: Any) -> SimpleNamespace:
    base = {"code": "crawler", "enabled": True, "daily_time": "10:10", "next_run_at": NOW, "version": 1}
    return SimpleNamespace(**(base | overrides))


def _run(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "job_code": "crawler",
        "status": "queued",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "available_at": NOW,
        "created_at": NOW,
        "sync_run_id": None,
        "error_message": None,
        "result": None,
    }
    return SimpleNamespace(**(base | overrides))


class _Session:
    """scalar/scalars 按调用顺序依次返回预设值。"""

    def __init__(self, scalars: list[Any] | None = None, scalar_values: list[Any] | None = None) -> None:
        self._scalar = list(scalar_values or [])
        self._scalars = list(scalars or [])
        self.added: list[Any] = []
        self.commit = AsyncMock()
        self.flush = AsyncMock()

    async def scalar(self, *_: Any) -> Any:
        return self._scalar.pop(0)

    async def scalars(self, *_: Any) -> Any:
        return SimpleNamespace(all=lambda: self._scalars.pop(0))

    def add(self, row: Any) -> None:
        self.added.append(row)


def test_mixins_build_the_tables_with_comments_and_the_active_run_guard() -> None:
    runs = _RunRow.__table__
    assert runs.comment == "测试执行记录" and all(col.comment for col in runs.columns)
    assert [fk.target_fullname for fk in runs.c.job_code.foreign_keys] == ["t_scheduled_jobs.code"]
    active = next(index for index in runs.indexes if index.name == "uq_scheduled_run_active")
    assert active.unique and "status IN" in str(active.dialect_options["postgresql"]["where"])


class TestRules:
    def test_daily_beijing_boundary_and_missed_days(self) -> None:
        assert next_daily(datetime(2026, 9, 29, 1, 59, tzinfo=UTC), "10:00") == datetime(2026, 9, 29, 2, tzinfo=UTC)
        assert next_daily(datetime(2026, 9, 29, 2, tzinfo=UTC), "10:00") == datetime(2026, 9, 30, 2, tzinfo=UTC)
        assert next_daily(datetime(2026, 12, 31, 23, tzinfo=UTC), "00:00") == datetime(2027, 1, 1, 16, tzinfo=UTC)

    @pytest.mark.parametrize("clock", ["24:00", "12:60", "9:00", "10:00:00", "", "$(whoami)"])
    def test_invalid_schedule_rejected(self, clock: str) -> None:
        with pytest.raises(ValidationError):
            JobUpdate(enabled=True, daily_time=clock, version=1)

    def test_arbitrary_command_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobUpdate(enabled=True, daily_time="10:00", version=1, command="ls")  # type: ignore[call-arg]

    def test_success_requires_the_batch_to_reach_success(self) -> None:
        assert claim_failure(None, "success") is None
        assert claim_failure("执行超过 30 分钟", "running") == "执行超过 30 分钟"
        assert claim_failure(None, "running") == "同步批次未成功完成"
        assert claim_failure(None, None) == "同步批次未成功完成"

    def test_retries_are_bounded(self) -> None:
        row = SimpleNamespace(attempts=1, finished_at=None)
        fail_run(row, "网络异常", NOW)
        assert row.status == "retrying" and (row.available_at - NOW).total_seconds() == 60
        row.attempts = 2
        fail_run(row, "网络异常", NOW)
        assert (row.available_at - NOW).total_seconds() == 300
        row.attempts = 3
        fail_run(row, "网络异常", NOW)
        assert row.status == "failed" and row.finished_at == NOW
        row.attempts = 1
        fail_run(row, "没选模板", NOW, retry=False)
        assert row.status == "failed"


class TestQueue:
    async def test_unknown_job_code_is_not_found(self) -> None:
        with pytest.raises(NotFoundError, match="任务不存在"):
            await _scheduler().get_job(_Session(), "rm -rf")  # type: ignore[arg-type]

    async def test_uninitialised_job_asks_for_a_migration(self) -> None:
        with pytest.raises(NotFoundError, match="数据库迁移"):
            await _scheduler().get_job(_Session(scalar_values=[None]), "crawler")  # type: ignore[arg-type]

    async def test_enqueue_refuses_a_second_active_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _scheduler()
        monkeypatch.setattr(s, "active_run", AsyncMock(return_value=_run()))
        with pytest.raises(VersionConflictError, match="请勿重复提交"):
            await s.enqueue(_Session(), _job(), NOW, trigger="manual", actor_name="张三")  # type: ignore[arg-type]

    async def test_scheduled_run_keeps_the_planned_time_and_manual_uses_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = _scheduler()
        monkeypatch.setattr(s, "active_run", AsyncMock(return_value=None))
        planned = NOW - timedelta(days=2)
        session = _Session()
        scheduled = await s.enqueue(session, _job(next_run_at=planned), NOW, trigger="scheduled", actor_name="每日计划")  # type: ignore[arg-type]
        manual = await s.enqueue(session, _job(next_run_at=planned), NOW, trigger="manual", actor_name="张三")  # type: ignore[arg-type]
        assert (scheduled.scheduled_at, manual.scheduled_at) == (planned, NOW)
        assert scheduled.status == "queued" and scheduled.attempts == 0

    async def test_missed_days_merge_into_one_run_and_next_plan_moves_forward(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = _scheduler()
        overdue = _job(next_run_at=NOW - timedelta(days=3))
        busy = _job(code="other", next_run_at=NOW - timedelta(days=1))
        monkeypatch.setattr(s, "active_run", AsyncMock(side_effect=[None, _run()]))
        enqueue = AsyncMock()
        monkeypatch.setattr(s, "enqueue", enqueue)
        await s.schedule_due(_Session(scalars=[[overdue, busy]]), NOW)  # type: ignore[arg-type]
        assert enqueue.await_count == 1
        assert overdue.next_run_at > NOW and busy.next_run_at > NOW

    async def test_history_attaches_each_batch_summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def summary(_s: Any, _id: uuid.UUID) -> dict[str, Any]:
            return {"status": "success"}

        s = _scheduler(crawler=Job("crawler", "爬虫", _noop, summary=summary))
        monkeypatch.setattr(s, "get_job", AsyncMock())
        monkeypatch.setattr(s, "run_data", lambda row: {"id": row.id})
        session = _Session(scalar_values=[7], scalars=[[_run(sync_run_id=uuid.uuid4())]])
        result = await s.history(session, "crawler", 1, 20)  # type: ignore[arg-type]
        assert result["total"] == 7 and result["items"][0]["result"] == {"status": "success"}


class TestUpdateJob:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        s = _scheduler()
        state = SimpleNamespace(s=s, job=_job(), active=None, events=[])
        monkeypatch.setattr(s, "get_job", AsyncMock(side_effect=lambda *_a, **_k: state.job))
        monkeypatch.setattr(s, "active_run", AsyncMock(side_effect=lambda *_: state.active))
        s._audit = AsyncMock(side_effect=lambda *_a, **k: state.events.append(k["event_type"]))
        return state

    async def test_stale_version_is_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(VersionConflictError):
            await env.s.update_job(object(), "crawler", ACTOR, enabled=True, daily_time="10:10", version=9)

    async def test_disabling_cancels_a_waiting_run_but_not_a_running_one(self, env: SimpleNamespace) -> None:
        env.active = _run(status="retrying")
        await env.s.update_job(object(), "crawler", ACTOR, enabled=False, daily_time="10:10", version=1)
        assert env.active.status == "cancelled" and env.active.finished_at is not None
        env.job, env.active = _job(), _run(status="running")
        await env.s.update_job(object(), "crawler", ACTOR, enabled=False, daily_time="10:10", version=1)
        assert env.active.status == "running"

    async def test_changing_the_clock_moves_the_next_run_and_bumps_the_version(self, env: SimpleNamespace) -> None:
        before = env.job.next_run_at
        await env.s.update_job(object(), "crawler", ACTOR, enabled=True, daily_time="11:30", version=1)
        assert env.job.daily_time == "11:30" and env.job.version == 2 and env.job.next_run_at != before
        assert env.events == ["scheduler.updated"]

    async def test_unchanged_plan_keeps_the_next_run(self, env: SimpleNamespace) -> None:
        before = env.job.next_run_at
        await env.s.update_job(object(), "crawler", ACTOR, enabled=True, daily_time="10:10", version=1)
        assert env.job.next_run_at == before


class TestTriggerAndOverview:
    async def test_manual_trigger_audits_with_the_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _scheduler()
        run = _run()
        monkeypatch.setattr(s, "get_job", AsyncMock(return_value=_job()))
        monkeypatch.setattr(s, "enqueue", AsyncMock(return_value=run))
        monkeypatch.setattr(s, "run_data", lambda row: {"id": row.id})
        audit = AsyncMock()
        s._audit = audit
        assert await s.trigger_job(object(), "crawler", ACTOR) == {"id": run.id}  # type: ignore[arg-type]
        assert audit.await_args is not None and audit.await_args.kwargs["extra"] == {"run_id": str(run.id)}

    async def test_worker_is_online_only_with_a_fresh_heartbeat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def watermark(_s: Any) -> datetime:
            return NOW

        s = _scheduler(
            crawler=Job("crawler", "爬虫监测增量同步", _noop, watermark=watermark), other=Job("other", "其他", _noop)
        )
        monkeypatch.setattr(s, "run_data", lambda row: {"id": row.id})

        class Session(_Session):
            def __init__(self, seen_at: datetime | None) -> None:
                # 库里多一条已退役的任务，页面不列。
                rows = [_job(code="other", enabled=False), _job(), _job(code="retired")]
                super().__init__(scalars=[rows, [], []])
                self.seen_at = seen_at

            async def get(self, *_: Any) -> Any:
                return SimpleNamespace(seen_at=self.seen_at) if self.seen_at else None

        fresh = await s.list_jobs(Session(datetime.now(UTC) - timedelta(seconds=10)))  # type: ignore[arg-type]
        stale = await s.list_jobs(Session(datetime.now(UTC) - timedelta(minutes=5)))  # type: ignore[arg-type]
        assert fresh["worker_online"] is True and stale["worker_online"] is False
        assert [item["code"] for item in fresh["items"]] == ["crawler", "other"]
        assert fresh["items"][0]["watermark"] == NOW and fresh["items"][1]["watermark"] is None
        assert fresh["items"][1]["next_run_at"] is None

    async def test_list_jobs_attaches_result_to_active_and_last_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def summary(_s: Any, _id: uuid.UUID) -> dict[str, Any]:
            return {"processed": 12}

        s = _scheduler(crawler=Job("crawler", "爬虫", _noop, summary=summary))
        monkeypatch.setattr(s, "run_data", lambda row: {"id": row.id})
        active = _run(status="running", sync_run_id=uuid.uuid4())
        last = _run(status="success", result={"processed": 50})

        class Session(_Session):
            def __init__(self) -> None:
                super().__init__(scalars=[[_job(), _job(code="other")], [last], [active]])

            async def get(self, *_: Any) -> Any:
                return None

        result = await s.list_jobs(Session())  # type: ignore[arg-type]
        assert result["items"][0]["active_run"] == {"id": active.id, "result": {"processed": 12}}
        assert result["items"][0]["last_run"] == {"id": last.id, "result": {"processed": 50}}

    async def test_run_status_carries_the_last_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _scheduler()
        last = _run(status="success", result={"status": "success"})
        monkeypatch.setattr(s, "active_run", AsyncMock(return_value=None))
        monkeypatch.setattr(s, "run_data", lambda row: {"id": row.id})
        status = await s.run_status(_Session(scalar_values=[last]), "crawler")  # type: ignore[arg-type]
        assert status == {"active_run": None, "last_run": {"id": last.id, "result": {"status": "success"}}}


class TestClaim:
    async def test_nothing_due_means_nothing_claimed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _scheduler()
        monkeypatch.setattr(s, "schedule_due", AsyncMock())
        assert await s.claim_next_run(_Session(scalar_values=[None]), NOW) is None  # type: ignore[arg-type]

    async def test_claim_marks_running_counts_the_attempt_and_creates_a_batch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = _scheduler()
        row = _run(status="retrying", attempts=1)
        monkeypatch.setattr(s, "schedule_due", AsyncMock())
        monkeypatch.setattr(s, "get_job", AsyncMock())
        monkeypatch.setattr(s, "active_run", AsyncMock(return_value=row))
        claimed = await s.claim_next_run(_Session(scalar_values=["crawler"]), NOW)  # type: ignore[arg-type]
        assert claimed == (row.id, "crawler", row.sync_run_id)
        assert row.status == "running" and row.attempts == 2 and row.started_at == NOW

    async def test_a_run_changed_by_someone_else_in_between_is_not_claimed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = _scheduler()
        monkeypatch.setattr(s, "schedule_due", AsyncMock())
        monkeypatch.setattr(s, "get_job", AsyncMock())
        monkeypatch.setattr(s, "active_run", AsyncMock(return_value=_run(status="cancelled")))
        assert await s.claim_next_run(_Session(scalar_values=["crawler"]), NOW) is None  # type: ignore[arg-type]


class TestLanes:
    def test_lanes_follow_registration_order_and_jobs_default_to_the_short_lane(self) -> None:
        s = _scheduler(a=Job("a", "甲", _noop), b=Job("b", "乙", _noop, lane=LONG_LANE), c=Job("c", "丙", _noop))
        assert s.lanes == [SHORT_LANE, LONG_LANE]
        assert (s.lane_codes(SHORT_LANE), s.lane_codes(LONG_LANE), s.lane_codes(None)) == (
            ["a", "c"],
            ["b"],
            ["a", "b", "c"],
        )

    async def test_a_lane_only_claims_its_own_jobs_but_every_due_plan_is_still_queued(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.dialects import postgresql

        s = _scheduler(sync=Job("sync", "同步", _noop), tagging=Job("tagging", "打标", _noop, lane=LONG_LANE))
        schedule = AsyncMock()
        monkeypatch.setattr(s, "schedule_due", schedule)
        asked: list[str] = []

        class Session(_Session):
            async def scalar(self, statement: Any) -> Any:
                compiled = statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
                asked.append(str(compiled))
                return None

        assert await s.claim_next_run(Session(), NOW, SHORT_LANE) is None  # type: ignore[arg-type]
        assert await s.claim_next_run(Session(), NOW, LONG_LANE) is None  # type: ignore[arg-type]
        assert await s.claim_next_run(Session(), NOW) is None  # type: ignore[arg-type]
        assert "IN ('sync')" in asked[0] and "IN ('tagging')" in asked[1] and "IN ('sync', 'tagging')" in asked[2]
        # 入队不分通道：长通道忙着的时候，到点的长任务也照样排上队。
        assert schedule.await_count == 3
