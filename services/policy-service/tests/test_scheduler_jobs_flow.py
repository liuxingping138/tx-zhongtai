"""调度应用层与仓储规则：停用取消排队、手动触发防重复、到点计划合并、领取任务。会话用脚本化替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import NotFoundError, VersionConflictError

from app.scheduler.application import jobs
from app.scheduler.repositories import jobs as repo

NOW = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)
ACTOR = SimpleNamespace(id="u1", name="管理员")


def _job(**overrides: Any) -> SimpleNamespace:
    base = {"code": "crawler-v2", "enabled": True, "daily_time": "10:10", "next_run_at": NOW, "version": 1}
    return SimpleNamespace(**(base | overrides))


def _run(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "job_code": "crawler-v2",
        "status": "queued",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "available_at": NOW,
        "created_at": NOW,
        "sync_run_id": None,
        "error_message": None,
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


class TestRepository:
    async def test_unknown_job_code_is_not_found(self) -> None:
        with pytest.raises(NotFoundError, match="任务不存在"):
            await repo.get_job(_Session(), "rm -rf")  # type: ignore[arg-type]

    async def test_uninitialised_job_asks_for_a_migration(self) -> None:
        with pytest.raises(NotFoundError, match="数据库迁移"):
            await repo.get_job(_Session(scalar_values=[None]), "crawler-v2")  # type: ignore[arg-type]

    async def test_enqueue_refuses_a_second_active_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(repo, "active_run", AsyncMock(return_value=_run()))
        with pytest.raises(VersionConflictError, match="请勿重复提交"):
            await repo.enqueue(_Session(), _job(), NOW, trigger="manual", actor_name="张三")  # type: ignore[arg-type]

    async def test_scheduled_run_keeps_the_planned_time_and_manual_uses_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(repo, "active_run", AsyncMock(return_value=None))
        planned = NOW - timedelta(days=2)
        session = _Session()
        scheduled = await repo.enqueue(
            session, _job(next_run_at=planned), NOW, trigger="scheduled", actor_name="每日计划"
        )  # type: ignore[arg-type]
        manual = await repo.enqueue(session, _job(next_run_at=planned), NOW, trigger="manual", actor_name="张三")  # type: ignore[arg-type]
        assert (scheduled.scheduled_at, manual.scheduled_at) == (planned, NOW)
        assert scheduled.status == "queued" and scheduled.attempts == 0

    async def test_missed_days_merge_into_one_run_and_next_plan_moves_forward(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        overdue = _job(next_run_at=NOW - timedelta(days=3))
        busy = _job(code="other", next_run_at=NOW - timedelta(days=1))
        monkeypatch.setattr(repo, "active_run", AsyncMock(side_effect=[None, _run()]))
        enqueue = AsyncMock()
        monkeypatch.setattr(repo, "enqueue", enqueue)
        await repo.schedule_due(_Session(scalars=[[overdue, busy]]), NOW)  # type: ignore[arg-type]
        assert enqueue.await_count == 1
        assert overdue.next_run_at > NOW and busy.next_run_at > NOW

    async def test_history_returns_rows_and_total(self) -> None:
        rows, total = await repo.history(_Session(scalar_values=[7], scalars=[[_run()]]), "crawler-v2", 1, 20)  # type: ignore[arg-type]
        assert total == 7 and len(rows) == 1


class TestUpdateJob:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(job=_job(), active=None, events=[])
        monkeypatch.setattr(jobs.repo, "get_job", AsyncMock(side_effect=lambda *_a, **_k: state.job))
        monkeypatch.setattr(jobs.repo, "active_run", AsyncMock(side_effect=lambda *_: state.active))
        monkeypatch.setattr(
            jobs, "enqueue_event", AsyncMock(side_effect=lambda *_a, **k: state.events.append(k["event_type"]))
        )
        return state

    async def test_stale_version_is_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(VersionConflictError):
            await jobs.update_job(object(), "crawler-v2", ACTOR, enabled=True, daily_time="10:10", version=9)  # type: ignore[arg-type,arg-type]

    async def test_disabling_cancels_a_waiting_run_but_not_a_running_one(self, env: SimpleNamespace) -> None:
        env.active = _run(status="retrying")
        await jobs.update_job(object(), "crawler-v2", ACTOR, enabled=False, daily_time="10:10", version=1)  # type: ignore[arg-type]
        assert env.active.status == "cancelled" and env.active.finished_at is not None
        env.job, env.active = _job(), _run(status="running")
        await jobs.update_job(object(), "crawler-v2", ACTOR, enabled=False, daily_time="10:10", version=1)  # type: ignore[arg-type]
        assert env.active.status == "running"

    async def test_changing_the_clock_moves_the_next_run_and_bumps_the_version(self, env: SimpleNamespace) -> None:
        before = env.job.next_run_at
        await jobs.update_job(object(), "crawler-v2", ACTOR, enabled=True, daily_time="11:30", version=1)  # type: ignore[arg-type]
        assert env.job.daily_time == "11:30" and env.job.version == 2 and env.job.next_run_at != before
        assert env.events == ["scheduler.updated"]

    async def test_unchanged_plan_keeps_the_next_run(self, env: SimpleNamespace) -> None:
        before = env.job.next_run_at
        await jobs.update_job(object(), "crawler-v2", ACTOR, enabled=True, daily_time="10:10", version=1)  # type: ignore[arg-type]
        assert env.job.next_run_at == before


class TestTriggerAndQueries:
    async def test_manual_trigger_audits_with_the_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = _run()
        monkeypatch.setattr(jobs.repo, "get_job", AsyncMock(return_value=_job()))
        monkeypatch.setattr(jobs.repo, "enqueue", AsyncMock(return_value=run))
        audit = AsyncMock()
        monkeypatch.setattr(jobs, "enqueue_event", audit)
        monkeypatch.setattr(jobs, "run_data", lambda row: {"id": row.id})
        assert await jobs.trigger_job(object(), "crawler-v2", ACTOR) == {"id": run.id}  # type: ignore[arg-type]
        assert audit.await_args.kwargs["extra"] == {"run_id": str(run.id)}

    async def test_worker_is_online_only_with_a_fresh_heartbeat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jobs, "run_data", lambda row: {"id": row.id})
        monkeypatch.setattr(jobs, "latest_watermark", AsyncMock(return_value=None))
        monkeypatch.setattr(jobs.repo, "active_run", AsyncMock(return_value=None))

        class Session(_Session):
            def __init__(self, seen_at: datetime | None) -> None:
                super().__init__(scalars=[[_job(), _job(enabled=False)]], scalar_values=[None, None])
                self.seen_at = seen_at

            async def get(self, *_: Any) -> Any:
                return SimpleNamespace(seen_at=self.seen_at) if self.seen_at else None

        fresh = await jobs.list_jobs(Session(datetime.now(UTC) - timedelta(seconds=10)))  # type: ignore[arg-type]
        stale = await jobs.list_jobs(Session(datetime.now(UTC) - timedelta(minutes=5)))  # type: ignore[arg-type]
        assert fresh["worker_online"] is True and stale["worker_online"] is False
        assert fresh["items"][1]["next_run_at"] is None
        assert fresh["items"][0]["name"] == "爬虫监测增量同步"

    async def test_history_attaches_the_sync_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jobs.repo, "get_job", AsyncMock())
        monkeypatch.setattr(jobs.repo, "history", AsyncMock(return_value=([_run()], 1)))
        monkeypatch.setattr(jobs, "sync_result", AsyncMock(return_value={"status": "success"}))
        monkeypatch.setattr(jobs, "run_data", lambda row: {"id": row.id})
        result = await jobs.history(object(), "crawler-v2", 1, 20)  # type: ignore[arg-type]
        assert result["items"][0]["result"] == {"status": "success"} and result["total"] == 1


class TestClaim:
    async def test_nothing_due_means_nothing_claimed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jobs.repo, "schedule_due", AsyncMock())
        assert await jobs.claim_next_run(_Session(scalar_values=[None]), NOW) is None  # type: ignore[arg-type]

    async def test_claim_marks_running_counts_the_attempt_and_creates_a_sync_batch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = _run(status="retrying", attempts=1)
        monkeypatch.setattr(jobs.repo, "schedule_due", AsyncMock())
        monkeypatch.setattr(jobs.repo, "get_job", AsyncMock())
        monkeypatch.setattr(jobs.repo, "active_run", AsyncMock(return_value=row))
        session = _Session(scalar_values=["crawler-v2"])
        claimed = await jobs.claim_next_run(session, NOW)  # type: ignore[arg-type]
        assert claimed == (row.id, "crawler-v2", row.sync_run_id)
        assert row.status == "running" and row.attempts == 2 and row.started_at == NOW

    async def test_a_run_changed_by_someone_else_in_between_is_not_claimed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(jobs.repo, "schedule_due", AsyncMock())
        monkeypatch.setattr(jobs.repo, "get_job", AsyncMock())
        monkeypatch.setattr(jobs.repo, "active_run", AsyncMock(return_value=_run(status="cancelled")))
        assert await jobs.claim_next_run(_Session(scalar_values=["crawler-v2"]), NOW) is None  # type: ignore[arg-type]
