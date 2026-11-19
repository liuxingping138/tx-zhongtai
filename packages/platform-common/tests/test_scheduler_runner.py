"""调度执行进程：执行一次领取到的任务并落记录、启动时回收被中断的任务、失败原因脱敏。会话和任务用替身。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from platform_common.scheduler import LONG_LANE, SHORT_LANE, Job, Scheduler, SchedulerRunner, UserFacingError
from platform_common.scheduler import runner as runner_module

from .scheduler_tables import tables


class _Db:
    """session_factory 的替身：同一个会话反复进出，记录提交次数。"""

    def __init__(self, rows: dict[Any, Any] | None = None, running: list[Any] | None = None) -> None:
        self.rows = rows or {}
        self.running = running or []
        self.statements: list[Any] = []
        self.commit = AsyncMock()

    def __call__(self) -> _Db:
        return self

    async def __aenter__(self) -> _Db:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _model: object, key: Any) -> Any:
        return self.rows.get(key)

    async def scalars(self, statement: Any) -> Any:
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.running)


def _row(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "job_code": "sync",
        "status": "running",
        "attempts": 1,
        "result": None,
        "finished_at": None,
        "error_message": None,
        "available_at": None,
        "sync_run_id": uuid.uuid4(),
    }
    return SimpleNamespace(**(base | overrides))


class _Batches:
    """有结果摘要的任务：记下收尾的原因，摘要按 status 返回。"""

    def __init__(self) -> None:
        self.status: str | None = "success"
        self.abandoned: list[str] = []
        self.execute = AsyncMock(return_value=None)

    async def abandon(self, _s: Any, _id: uuid.UUID, message: str) -> None:
        self.abandoned.append(message)

    async def summary(self, _s: Any, _id: uuid.UUID) -> dict[str, Any] | None:
        return {"status": self.status} if self.status else None


@pytest.fixture
def batches() -> _Batches:
    return _Batches()


def _runner(db: _Db, batches: _Batches, **job: Any) -> SchedulerRunner:
    async def execute(batch_id: uuid.UUID) -> dict[str, Any] | None:
        result: dict[str, Any] | None = await batches.execute(batch_id)
        return result

    jobs = [
        Job(
            "sync",
            "同步",
            execute,
            timeout_seconds=job.get("timeout", 60),
            abandon=batches.abandon,
            summary=batches.summary,
            public_errors=("已有同步正在运行",),
        ),
        Job("cleanup", "清理", execute),
        Job("tagging", "打标", execute, timeout_seconds=6 * 3600, lane=LONG_LANE),
    ]
    scheduler = Scheduler(jobs=jobs, **tables(), audit=AsyncMock())
    return SchedulerRunner(
        scheduler,
        engine=AsyncMock(),
        session_factory=db,
        leader_lock=1,
        logger_name="test.scheduler",  # type: ignore[arg-type]
    )


class TestExecuteClaim:
    async def test_successful_batch_marks_the_run_success(self, batches: _Batches) -> None:
        row = _row()
        db = _Db({row.id: row})
        await _runner(db, batches).execute_claim((row.id, "sync", row.sync_run_id))
        assert row.status == "success" and row.finished_at is not None and row.error_message is None
        assert row.result == {"status": "success"}
        db.commit.assert_awaited_once()

    async def test_a_job_without_summary_succeeds_when_it_does_not_raise(self, batches: _Batches) -> None:
        row = _row(job_code="cleanup")
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "cleanup", row.sync_run_id))
        assert row.status == "success" and row.result is None and not batches.abandoned

    async def test_what_a_simple_job_returns_becomes_the_result(self, batches: _Batches) -> None:
        row = _row(job_code="cleanup")
        batches.execute.return_value = {"deleted": 3}
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "cleanup", row.sync_run_id))
        assert row.status == "success" and row.result == {"deleted": 3}

    async def test_error_is_stored_safely_and_scheduled_for_retry(self, batches: _Batches) -> None:
        row = _row(attempts=1)
        batches.execute.side_effect = ValueError("mysql://user:secret@host")
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "sync", row.sync_run_id))
        assert row.status == "retrying"
        assert "secret" not in row.error_message and "ValueError" in row.error_message
        assert batches.abandoned and "secret" not in batches.abandoned[0]

    async def test_setting_problems_fail_at_once_without_retrying(self, batches: _Batches) -> None:
        row = _row(attempts=1)
        reason = "还没有选上线模板，请在任务调度页这个任务的设置里选"
        batches.execute.side_effect = UserFacingError(reason)
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "sync", row.sync_run_id))
        assert (row.status, row.error_message) == ("failed", reason) and row.finished_at is not None

    async def test_attempt_budget_exhausted_ends_as_failed_with_the_public_message(self, batches: _Batches) -> None:
        row = _row(attempts=3)
        batches.execute.side_effect = RuntimeError("已有同步正在运行")
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "sync", row.sync_run_id))
        assert row.status == "failed" and row.error_message == "已有同步正在运行"

    async def test_a_batch_that_never_reached_success_is_not_reported_as_success(self, batches: _Batches) -> None:
        batches.status = "running"
        row = _row(attempts=1)
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "sync", row.sync_run_id))
        assert row.status == "retrying" and row.error_message == "同步批次未成功完成"

    async def test_timeout_is_reported_in_plain_words(self, batches: _Batches) -> None:
        row = _row(attempts=3)

        async def slow(*_: Any) -> None:
            await asyncio.sleep(1)

        batches.execute.side_effect = slow
        await _runner(_Db({row.id: row}), batches, timeout=0.01).execute_claim((row.id, "sync", row.sync_run_id))
        assert "执行超过 0 分钟" in row.error_message and "已中止本次执行" in row.error_message

    async def test_unknown_job_is_refused_without_retrying(self, batches: _Batches) -> None:
        row = _row(job_code="gone")
        await _runner(_Db({row.id: row}), batches).execute_claim((row.id, "gone", row.sync_run_id))
        assert (row.status, row.error_message) == ("failed", "未知任务，拒绝执行")

    async def test_missing_run_record_is_an_error(self, batches: _Batches) -> None:
        with pytest.raises(RuntimeError, match="执行记录丢失"):
            await _runner(_Db(), batches).execute_claim((uuid.uuid4(), "sync", uuid.uuid4()))


class TestRecover:
    async def test_a_finished_batch_is_recorded_as_success(self, batches: _Batches) -> None:
        row = _row()
        db = _Db(running=[row])
        await _runner(db, batches).recover_interrupted()
        assert row.status == "success" and row.result == {"status": "success"}
        db.commit.assert_awaited_once()

    async def test_an_unfinished_batch_is_closed_and_retried(self, batches: _Batches) -> None:
        batches.status = "running"
        row = _row(attempts=1)
        await _runner(_Db(running=[row]), batches).recover_interrupted()
        assert row.status == "retrying" and "进程中断" in row.error_message
        assert batches.abandoned

    async def test_a_job_without_summary_is_rerun_after_an_interruption(self, batches: _Batches) -> None:
        row = _row(job_code="cleanup", attempts=1)
        await _runner(_Db(running=[row]), batches).recover_interrupted()
        assert row.status == "retrying"

    async def test_recovering_one_lane_leaves_the_other_lanes_runs_alone(self, batches: _Batches) -> None:
        from sqlalchemy.dialects import postgresql

        db = _Db()
        runner = _runner(db, batches)
        await runner.recover_interrupted()
        await runner.recover_interrupted(SHORT_LANE)
        whole, lane = (
            str(item.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            for item in db.statements
        )
        assert "job_code IN" not in whole
        assert "IN ('sync', 'cleanup')" in lane and "tagging" not in lane


class TestSafeError:
    def test_public_messages_pass_through_only_for_their_job(self, batches: _Batches) -> None:
        runner = _runner(_Db(), batches)
        assert runner.safe_error(RuntimeError("已有同步正在运行"), "sync") == "已有同步正在运行"
        assert "已有同步" not in runner.safe_error(RuntimeError("已有同步正在运行"), "cleanup")

    def test_other_runtime_errors_do_not_leak_their_text(self, batches: _Batches) -> None:
        message = _runner(_Db(), batches).safe_error(RuntimeError("connect failed password=hunter2"), "sync")
        assert "hunter2" not in message


class TestHealth:
    async def test_healthy_only_with_a_fresh_heartbeat(self, batches: _Batches) -> None:
        fresh = _Db({1: SimpleNamespace(seen_at=datetime.now(UTC) - timedelta(seconds=10))})
        stale = _Db({1: SimpleNamespace(seen_at=datetime.now(UTC) - timedelta(minutes=5))})
        assert await _runner(fresh, batches).healthy() is True
        assert await _runner(stale, batches).healthy() is False
        assert await _runner(_Db(), batches).healthy() is False


async def _until(condition: Any) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("等不到预期的状态")


class TestLoop:
    async def test_a_lane_recovers_first_then_runs_claims_until_cancelled(self, batches: _Batches) -> None:
        runner = _runner(_Db(), batches)
        claim = (uuid.uuid4(), "sync", uuid.uuid4())
        calls: list[str] = []
        runner.claim_next = AsyncMock(side_effect=[claim, asyncio.CancelledError()])  # type: ignore[method-assign]
        runner.execute_claim = AsyncMock(side_effect=lambda c: calls.append("execute"))  # type: ignore[method-assign]
        with pytest.raises(asyncio.CancelledError):
            await runner.drain(SHORT_LANE)
        assert calls == ["execute"]
        assert [call.args for call in runner.claim_next.await_args_list] == [(SHORT_LANE,), (SHORT_LANE,)]

    async def test_a_long_job_does_not_hold_up_the_short_lane(
        self, batches: _Batches, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "POLL_SECONDS", 0.005)
        runner = _runner(_Db(), batches)
        tagging = (uuid.uuid4(), "tagging", uuid.uuid4())
        sync = (uuid.uuid4(), "sync", uuid.uuid4())
        queues: dict[str, list[Any]] = {LONG_LANE: [tagging], SHORT_LANE: [None, sync]}
        asked: dict[str, int] = {SHORT_LANE: 0, LONG_LANE: 0}
        release = asyncio.Event()
        done: list[str] = []

        async def claim_next(lane: str | None = None) -> Any:
            assert lane is not None
            asked[lane] += 1
            return queues[lane].pop(0) if queues[lane] else None

        async def execute_claim(claim: tuple[uuid.UUID, str, uuid.UUID]) -> None:
            if claim is tagging:
                await release.wait()
            done.append(claim[1])

        recover = AsyncMock()
        runner.recover_interrupted = recover  # type: ignore[method-assign]
        runner.claim_next = claim_next  # type: ignore[method-assign]
        runner.execute_claim = execute_claim  # type: ignore[method-assign]
        consume = asyncio.create_task(runner.consume())
        try:
            await _until(lambda: done == ["sync"])
            # 打标还在跑：短通道照样执行完同步，长通道这段时间不再领第二条。
            assert asked[LONG_LANE] == 1
            release.set()
            await _until(lambda: "tagging" in done)
        finally:
            consume.cancel()
            with pytest.raises(asyncio.CancelledError):
                await consume
        # leader 接手时全部回收一次，之后各通道不再回收。
        recover.assert_awaited_once_with()

    async def test_a_failed_claim_keeps_other_lanes_running_and_recovers_its_own_lane_first(
        self, batches: _Batches, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "POLL_SECONDS", 0)
        runner = _runner(_Db(), batches)
        claim = (uuid.uuid4(), "sync", uuid.uuid4())
        calls: list[Any] = []
        runner.claim_next = AsyncMock(side_effect=[OSError("db down"), claim, asyncio.CancelledError()])  # type: ignore[method-assign]
        runner.recover_interrupted = AsyncMock(side_effect=lambda lane=None: calls.append(("recover", lane)))  # type: ignore[method-assign]
        runner.execute_claim = AsyncMock(side_effect=lambda c: calls.append("execute"))  # type: ignore[method-assign]
        with pytest.raises(asyncio.CancelledError):
            await runner.drain(SHORT_LANE)
        # 那次领取可能已经提交、只是回包丢了：先把本通道停在 running 的收回来再接着领。
        assert calls == [("recover", SHORT_LANE), "execute"]

    async def test_a_lane_that_cannot_record_its_result_stops_every_lane_for_the_leader_to_recover(
        self, batches: _Batches, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "POLL_SECONDS", 0.005)
        runner = _runner(_Db(), batches)
        tagging = (uuid.uuid4(), "tagging", uuid.uuid4())
        sync = (uuid.uuid4(), "sync", uuid.uuid4())
        queues: dict[str, list[Any]] = {LONG_LANE: [tagging], SHORT_LANE: [None, sync]}
        cancelled: list[str] = []

        async def claim_next(lane: str | None = None) -> Any:
            assert lane is not None
            return queues[lane].pop(0) if queues[lane] else None

        async def execute_claim(claim: tuple[uuid.UUID, str, uuid.UUID]) -> None:
            if claim is sync:
                raise RuntimeError("执行记录丢失")
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.append(claim[1])
                raise

        runner.recover_interrupted = AsyncMock()  # type: ignore[method-assign]
        runner.claim_next = claim_next  # type: ignore[method-assign]
        runner.execute_claim = execute_claim  # type: ignore[method-assign]
        with pytest.raises(ExceptionGroup):
            await asyncio.wait_for(runner.consume(), timeout=1)
        assert cancelled == ["tagging"]

    async def test_a_service_without_jobs_still_polls_instead_of_spinning_on_the_lock(
        self, batches: _Batches, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "POLL_SECONDS", 0.005)
        runner = _runner(_Db(), batches)
        runner.scheduler.lanes = []
        runner.recover_interrupted = AsyncMock()  # type: ignore[method-assign]
        runner.claim_next = AsyncMock(return_value=None)  # type: ignore[method-assign]
        consume = asyncio.create_task(runner.consume())
        await _until(lambda: runner.claim_next.await_count >= 2)
        assert not consume.done()
        consume.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consume

    async def test_run_keeps_retrying_when_the_database_is_down_and_stops_on_signal(self, batches: _Batches) -> None:
        runner = _runner(_Db(), batches)
        stop = asyncio.Event()

        async def lead(_stop: asyncio.Event) -> None:
            stop.set()
            raise OSError("connection refused")

        runner.lead = lead  # type: ignore[method-assign]
        await asyncio.wait_for(runner.run(stop), timeout=1)

    async def test_disabled_scheduled_job_does_not_retry_on_failure(self, batches: _Batches) -> None:
        row = _row(job_code="sync", trigger="scheduled", attempts=1)
        disabled_job = SimpleNamespace(code="sync", enabled=False)
        db = _Db(rows={row.id: row, "sync": disabled_job})
        batches.execute.side_effect = RuntimeError("transient network error")
        runner = _runner(db, batches)

        await runner.execute_claim((row.id, "sync", row.sync_run_id))

        assert row.status == "failed"
        assert row.finished_at is not None
