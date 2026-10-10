from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

import pytest
from pydantic import ValidationError

from app.scheduler.api.jobs import JobUpdate
from app.scheduler.application.jobs import claim_failure
from app.scheduler.domain.scheduling import next_daily
from app.worker.scheduler import fail_run, safe_error


def test_daily_beijing_boundary_and_missed_days():
    assert next_daily(datetime(2026, 9, 29, 1, 59, tzinfo=UTC), "10:00") == datetime(2026, 9, 29, 2, tzinfo=UTC)
    assert next_daily(datetime(2026, 9, 29, 2, tzinfo=UTC), "10:00") == datetime(2026, 9, 30, 2, tzinfo=UTC)
    assert next_daily(datetime(2026, 12, 31, 23, tzinfo=UTC), "00:00") == datetime(2027, 1, 1, 16, tzinfo=UTC)


@pytest.mark.parametrize("clock", ["24:00", "12:60", "9:00", "10:00:00", "", "$(whoami)"])
def test_invalid_schedule_rejected(clock):
    with pytest.raises(ValidationError):
        JobUpdate(enabled=True, daily_time=clock, version=1)


def test_arbitrary_command_rejected():
    with pytest.raises(ValidationError):
        JobUpdate(enabled=True, daily_time="10:00", version=1, command="ls")


def test_scheduled_success_requires_sync_batch_success():
    assert claim_failure(None, "success") is None
    assert claim_failure("同步超过 30 分钟，已中止本次执行", "running") == "同步超过 30 分钟，已中止本次执行"
    assert claim_failure(None, "running") == "同步批次未成功完成"
    assert claim_failure(None, None) == "同步批次未成功完成"


def test_retries_bounded_and_error_safe():
    now = datetime.now(UTC)
    row = SimpleNamespace(attempts=1, finished_at=None)
    fail_run(row, "网络异常", now)
    assert row.status == "retrying" and (row.available_at - now).total_seconds() == 60
    row.attempts = 2
    fail_run(row, "网络异常", now)
    assert (row.available_at - now).total_seconds() == 300
    row.attempts = 3
    fail_run(row, "网络异常", now)
    assert row.status == "failed" and row.finished_at == now
    assert "secret" not in safe_error(ValueError("mysql://user:secret@host"))
