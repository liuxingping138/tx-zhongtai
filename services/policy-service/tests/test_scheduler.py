"""政策服务登记的定时任务：页面顺序、超时、能原样显示的失败原因，以及爬虫任务的前置条件、收尾和摘要。

调度引擎本身的规则（排队、重试、回收、脱敏）在 platform-common 的测试里。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.scheduler import LONG_LANE, SHORT_LANE, SchedulerRunner

from app.aitag.domain.tasks import TASKS, job_code
from app.scheduler.application import jobs
from app.worker.scheduler import runner


class _Db:
    def __init__(self, row: Any = None) -> None:
        self.row = row

    def __call__(self) -> _Db:
        return self

    async def __aenter__(self) -> _Db:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, *_: Any) -> Any:
        return self.row


def test_jobs_are_listed_in_page_order_with_their_own_timeouts() -> None:
    registered = jobs.scheduler.jobs
    assert list(registered) == ["crawler", "crawler_config", *(job_code(task) for task in TASKS)]
    assert [registered[job_code(task)].name for task in TASKS] == ["政策类型判断", "政策解读", "政策市场机会"]
    assert registered["crawler"].timeout_seconds == 1800 and registered["crawler_config"].timeout_seconds == 600
    assert all(registered[job_code(task)].timeout_seconds == 6 * 3600 for task in TASKS)
    # 每个任务都能收尾和给出摘要：执行记录只认批次写成 success。
    assert all(job.abandon and job.summary for job in registered.values())


def test_tagging_runs_in_its_own_lane_so_syncs_do_not_wait_hours_behind_it() -> None:
    registered = jobs.scheduler.jobs
    assert {registered[job_code(task)].lane for task in TASKS} == {LONG_LANE}
    assert registered["crawler"].lane == registered["crawler_config"].lane == SHORT_LANE
    assert jobs.scheduler.lanes == [SHORT_LANE, LONG_LANE]


def test_the_worker_runs_this_services_scheduler() -> None:
    assert isinstance(runner, SchedulerRunner) and runner.scheduler is jobs.scheduler


@pytest.mark.parametrize("message", ["尚未建立同步水位，请先回填", "已有爬虫同步正在运行"])
def test_crawler_business_messages_pass_through(message: str) -> None:
    assert runner.safe_error(RuntimeError(message), "crawler") == message


def test_six_hour_timeout_is_reported_for_tagging() -> None:
    assert "360 分钟" in runner.safe_error(TimeoutError(), job_code("interpret"))


class TestCrawlerJob:
    async def test_without_a_watermark_it_refuses_instead_of_running_a_short_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(jobs, "SessionLocal", _Db())
        monkeypatch.setattr(jobs, "crawler_watermark", AsyncMock(return_value=None))
        run = AsyncMock()
        monkeypatch.setattr(jobs, "run_crawler_sync", run)
        with pytest.raises(RuntimeError, match="首次历史回填"):
            await jobs.run_crawler(uuid.uuid4())
        run.assert_not_awaited()

    async def test_with_a_watermark_it_runs_incrementally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jobs, "SessionLocal", _Db())
        monkeypatch.setattr(jobs, "crawler_watermark", AsyncMock(return_value=datetime.now(UTC)))
        run = AsyncMock()
        monkeypatch.setattr(jobs, "run_crawler_sync", run)
        sync_id = uuid.uuid4()
        await jobs.run_crawler(sync_id)
        run.assert_awaited_once_with(mode="incremental", run_id=sync_id)

    async def test_abandon_closes_only_a_running_batch(self) -> None:
        running = SimpleNamespace(status="running", error_message=None, finished_at=None)
        await jobs.abandon_crawler(_Db(running), uuid.uuid4(), "超时")  # type: ignore[arg-type]
        assert running.status == "failed" and running.error_message == "超时" and running.finished_at
        done = SimpleNamespace(status="success", error_message=None)
        await jobs.abandon_crawler(_Db(done), uuid.uuid4(), "超时")  # type: ignore[arg-type]
        assert done.status == "success"

    async def test_summary_keeps_filled_fields_as_text(self) -> None:
        batch = SimpleNamespace(
            date_from=datetime(2026, 10, 1, tzinfo=UTC),
            date_to=None,
            watermark=None,
            status="success",
            days_synced=3,
            site_rows=12,
        )
        summary = await jobs.crawler_summary(_Db(batch), uuid.uuid4())  # type: ignore[arg-type]
        assert summary == {
            "date_from": "2026-10-01T00:00:00+00:00",
            "status": "success",
            "days_synced": 3,
            "site_rows": 12,
        }
        assert await jobs.crawler_summary(_Db(), uuid.uuid4()) is None  # type: ignore[arg-type]


async def test_tagging_jobs_call_their_own_task(monkeypatch: pytest.MonkeyPatch) -> None:
    run_batch, abandon, summary = AsyncMock(), AsyncMock(), AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(jobs.tagging, "run_batch", run_batch)
    monkeypatch.setattr(jobs.tagging, "abandon", abandon)
    monkeypatch.setattr(jobs.tagging, "summary", summary)
    job = jobs.tagging_job("interpret", "政策解读")
    run_id = uuid.uuid4()
    await job.execute(run_id)
    assert job.abandon and job.summary
    await job.abandon(object(), run_id, "中断")  # type: ignore[arg-type]
    assert await job.summary(object(), run_id) == {"status": "success"}  # type: ignore[arg-type]
    run_batch.assert_awaited_once_with(run_id, "interpret")
    abandon.assert_awaited_once_with(run_id, "中断")
