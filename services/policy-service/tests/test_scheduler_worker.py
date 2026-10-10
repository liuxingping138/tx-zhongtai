"""调度进程：执行一次领取到的任务并落记录、启动时回收被中断的任务、同步前置条件。会话和同步用替身。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.worker import scheduler as worker


class _Db:
    """SessionLocal 的替身：同一个会话反复进出，记录提交次数。"""

    def __init__(self, rows: dict[uuid.UUID, Any] | None = None, running: list[Any] | None = None) -> None:
        self.rows = rows or {}
        self.running = running or []
        self.commit = AsyncMock()

    def __call__(self) -> _Db:
        return self

    async def __aenter__(self) -> _Db:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _model: object, key: uuid.UUID) -> Any:
        return self.rows.get(key)

    async def scalars(self, *_: Any) -> Any:
        return SimpleNamespace(all=lambda: self.running)


def _row(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "status": "running",
        "attempts": 1,
        "result": None,
        "finished_at": None,
        "error_message": None,
        "available_at": None,
    }
    return SimpleNamespace(**(base | overrides))


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(result={"status": "success"}, abandoned=[])

    async def abandon(_s: object, row: Any, message: str) -> None:
        state.abandoned.append(message)

    monkeypatch.setattr(worker, "abandon_running_sync", abandon)
    monkeypatch.setattr(worker, "sync_result", AsyncMock(side_effect=lambda *_: state.result))
    return state


class TestExecuteClaim:
    async def test_successful_sync_marks_the_run_success(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        row = _row()
        db = _Db({row.id: row})
        monkeypatch.setattr(worker, "SessionLocal", db)
        monkeypatch.setattr(worker, "execute_sync", AsyncMock())
        await worker.execute_claim((row.id, "crawler-v2", uuid.uuid4()))
        assert row.status == "success" and row.finished_at is not None and row.error_message is None
        db.commit.assert_awaited_once()

    async def test_sync_error_is_stored_safely_and_scheduled_for_retry(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        row = _row(attempts=1)
        monkeypatch.setattr(worker, "SessionLocal", _Db({row.id: row}))
        monkeypatch.setattr(worker, "execute_sync", AsyncMock(side_effect=ValueError("mysql://user:secret@host")))
        await worker.execute_claim((row.id, "crawler-v2", uuid.uuid4()))
        assert row.status == "retrying"
        assert "secret" not in row.error_message and "ValueError" in row.error_message
        assert patched.abandoned and "secret" not in patched.abandoned[0]

    async def test_attempt_budget_exhausted_ends_as_failed(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        row = _row(attempts=3)
        monkeypatch.setattr(worker, "SessionLocal", _Db({row.id: row}))
        monkeypatch.setattr(worker, "execute_sync", AsyncMock(side_effect=RuntimeError("已有爬虫同步正在运行")))
        await worker.execute_claim((row.id, "crawler-v2", uuid.uuid4()))
        assert row.status == "failed" and row.error_message == "已有爬虫同步正在运行"

    async def test_a_batch_that_never_reached_success_is_not_reported_as_success(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        patched.result = {"status": "running"}
        row = _row(attempts=1)
        monkeypatch.setattr(worker, "SessionLocal", _Db({row.id: row}))
        monkeypatch.setattr(worker, "execute_sync", AsyncMock())
        await worker.execute_claim((row.id, "crawler-v2", uuid.uuid4()))
        assert row.status == "retrying" and row.error_message == "同步批次未成功完成"

    async def test_timeout_is_reported_in_plain_words(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        row = _row(attempts=3)
        monkeypatch.setattr(worker, "SessionLocal", _Db({row.id: row}))
        monkeypatch.setattr(worker, "TIMEOUT_SECONDS", 0.01)

        async def slow(*_: Any) -> None:
            await asyncio.sleep(1)

        monkeypatch.setattr(worker, "execute_sync", slow)
        await worker.execute_claim((row.id, "crawler-v2", uuid.uuid4()))
        assert "30 分钟" in row.error_message

    async def test_missing_run_record_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        monkeypatch.setattr(worker, "SessionLocal", _Db())
        monkeypatch.setattr(worker, "execute_sync", AsyncMock())
        with pytest.raises(RuntimeError, match="执行记录丢失"):
            await worker.execute_claim((uuid.uuid4(), "crawler-v2", uuid.uuid4()))


class TestExecuteSync:
    async def test_without_a_watermark_it_refuses_instead_of_running_a_short_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker, "SessionLocal", _Db())
        monkeypatch.setattr(worker, "latest_watermark", AsyncMock(return_value=None))
        run = AsyncMock()
        monkeypatch.setattr(worker, "run_v2", run)
        with pytest.raises(RuntimeError, match="首次历史回填"):
            await worker.execute_sync("crawler-v2", uuid.uuid4())
        run.assert_not_awaited()

    async def test_known_job_runs_incrementally_and_unknown_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker, "SessionLocal", _Db())
        monkeypatch.setattr(worker, "latest_watermark", AsyncMock(return_value=datetime.now(UTC)))
        run = AsyncMock()
        monkeypatch.setattr(worker, "run_v2", run)
        sync_id = uuid.uuid4()
        await worker.execute_sync("crawler-v2", sync_id)
        run.assert_awaited_once_with(mode="incremental", run_id=sync_id)
        with pytest.raises(RuntimeError, match="未知任务"):
            await worker.execute_sync("crawler-v1", sync_id)


class TestRecover:
    async def test_a_finished_batch_is_recorded_as_success(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        row = _row()
        db = _Db(running=[row])
        monkeypatch.setattr(worker, "SessionLocal", db)
        await worker.recover_interrupted()
        assert row.status == "success" and row.result == {"status": "success"}
        db.commit.assert_awaited_once()

    async def test_an_unfinished_batch_is_closed_and_retried(
        self, monkeypatch: pytest.MonkeyPatch, patched: SimpleNamespace
    ) -> None:
        patched.result = {"status": "running"}
        row = _row(attempts=1)
        monkeypatch.setattr(worker, "SessionLocal", _Db(running=[row]))
        await worker.recover_interrupted()
        assert row.status == "retrying" and "进程中断" in row.error_message
        assert patched.abandoned


class TestSafeError:
    @pytest.mark.parametrize("message", ["尚未建立同步水位，请先回填", "已有爬虫同步正在运行", "未知任务，拒绝执行"])
    def test_known_business_messages_pass_through(self, message: str) -> None:
        assert worker.safe_error(RuntimeError(message)) == message

    def test_other_runtime_errors_do_not_leak_their_text(self) -> None:
        assert "password=hunter2" not in worker.safe_error(RuntimeError("connect failed password=hunter2"))
