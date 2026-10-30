"""只在显式指定的全新 scheduler_test 库运行，不接真实爬虫源。"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from platform_common.actors import Actor
from platform_common.errors import PermissionDeniedError, VersionConflictError
from platform_common.scheduler import LONG_LANE, SHORT_LANE
from sqlalchemy import delete, text

from app.aitag.domain.tasks import job_code
from app.common.security import get_authz_client
from app.core.database import SessionLocal, engine
from app.crawler.domain.models import CrawlerSyncRun
from app.main import app
from app.scheduler.application.jobs import run_crawler, scheduler
from app.scheduler.domain.models import ScheduledRun
from app.scheduler.domain.scheduling import LEADER_LOCK
from app.worker.scheduler import runner

pytestmark = pytest.mark.skipif(os.environ.get("SCHEDULER_INTEGRATION") != "1", reason="需要独立 scheduler_test 数据库")
ACTOR = Actor(id=str(uuid.uuid4()), name="调度验收")


@pytest_asyncio.fixture(autouse=True)
async def isolated():
    assert engine.url.database == "scheduler_test", "拒绝在业务数据库执行破坏性测试"
    async with SessionLocal() as session:
        await session.execute(delete(ScheduledRun))
        await session.execute(delete(CrawlerSyncRun))
        await session.execute(
            text(
                "UPDATE policy_scheduled_jobs SET enabled=true, daily_time='10:00', "
                "next_run_at=now()+interval '1 day', version=1"
            )
        )
        await session.commit()
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


async def trigger(code="crawler"):
    async with SessionLocal() as session:
        row = await scheduler.trigger_job(session, code, ACTOR)
        await session.commit()
        return row


async def test_parallel_manual_requests_coalesce():
    results = await asyncio.gather(trigger(), trigger(), return_exceptions=True)
    assert sum(isinstance(x, dict) for x in results) == 1
    assert sum(isinstance(x, VersionConflictError) for x in results) == 1
    async with SessionLocal() as session:
        assert (await scheduler.history(session, "crawler", 1, 20))["total"] == 1


async def test_missed_days_catch_up_once_and_manual_race():
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        job = await scheduler.get_job(session, "crawler", lock=True)
        job.next_run_at = now - timedelta(days=4)
        await session.commit()

    async def schedule():
        async with SessionLocal() as session:
            await scheduler.schedule_due(session, now)
            await session.commit()

    results = await asyncio.gather(schedule(), trigger(), return_exceptions=True)
    assert all(x is None or isinstance(x, (dict, VersionConflictError)) for x in results)
    await schedule()
    async with SessionLocal() as session:
        page = await scheduler.history(session, "crawler", 1, 20)
        assert page["total"] == 1 and page["items"][0]["status"] == "queued"
        assert (await scheduler.get_job(session, "crawler")).next_run_at > now


async def test_pause_cancels_pending_and_version_conflict():
    await trigger()
    async with SessionLocal() as session:
        await scheduler.update_job(session, "crawler", ACTOR, enabled=False, daily_time="11:00", version=1)
        await session.commit()
        assert (await scheduler.history(session, "crawler", 1, 20))["items"][0]["status"] == "cancelled"
    async with SessionLocal() as session:
        with pytest.raises(VersionConflictError):
            await scheduler.update_job(session, "crawler", ACTOR, enabled=True, daily_time="12:00", version=1)
    # 停用计划后仍允许一次手动执行。
    assert (await trigger())["status"] == "queued"


async def test_failure_retry_success_and_saved_result(monkeypatch):
    await trigger()
    claim = await runner.claim_next()
    assert claim
    monkeypatch.setattr(runner, "execute", AsyncMock(side_effect=ValueError("secret")))
    await runner.execute_claim(claim)
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "retrying" and row.attempts == 1 and "secret" not in row.error_message
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    next_claim = await runner.claim_next()
    assert next_claim and next_claim[2] != claim[2]

    async def success(code, sync_id):
        async with SessionLocal() as session:
            session.add(
                CrawlerSyncRun(
                    id=sync_id,
                    mode="incremental",
                    started_at=datetime.now(UTC),
                    status="success",
                    days_synced=4,
                    site_rows=12,
                    watermark=datetime.now(UTC),
                )
            )
            await session.commit()

    monkeypatch.setattr(runner, "execute", success)
    await runner.execute_claim(next_claim)
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "success" and row.attempts == 2 and row.error_message is None
        assert row.result["site_rows"] == 12


async def test_recovery_does_not_repeat_completed_sync():
    await trigger()
    claim = await runner.claim_next()
    async with SessionLocal() as session:
        session.add(
            CrawlerSyncRun(
                id=claim[2],
                mode="incremental",
                started_at=datetime.now(UTC),
                status="success",
                days_synced=1,
                site_rows=4,
            )
        )
        await session.commit()
    await runner.recover_interrupted()
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "success" and row.result["site_rows"] == 4
    assert await runner.claim_next() is None


async def test_timeout_closes_running_sync_batch(monkeypatch):
    await trigger()
    claim = await runner.claim_next()
    assert claim

    # 先持久化已运行批次，再测试超时清理；不能假设远端 DB 在 50ms 内提交。
    async with SessionLocal() as session:
        session.add(
            CrawlerSyncRun(
                id=claim[2],
                mode="incremental",
                started_at=datetime.now(UTC),
                status="running",
                days_synced=0,
                site_rows=0,
            )
        )
        await session.commit()

    async def hang(_code, sync_id):
        assert sync_id == claim[2]
        await asyncio.sleep(30)

    monkeypatch.setattr(runner, "execute", hang)
    monkeypatch.setitem(scheduler.jobs, "crawler", dataclasses.replace(scheduler.jobs["crawler"], timeout_seconds=0.05))
    await runner.execute_claim(claim)
    async with SessionLocal() as session:
        scheduled = await session.get(ScheduledRun, claim[0])
        sync = await session.get(CrawlerSyncRun, claim[2])
        assert scheduled is not None and scheduled.status == "retrying"
        assert sync is not None and sync.status == "failed"
        assert sync.error_message


async def test_recovery_retries_interrupted_run_and_global_lock():
    await trigger()
    claim = await runner.claim_next()
    await runner.recover_interrupted()
    async with SessionLocal() as session:
        assert (await session.get(ScheduledRun, claim[0])).status == "retrying"
    async with engine.connect() as first, engine.connect() as second:
        assert await first.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK})
        try:
            assert not await second.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK})
        finally:
            await first.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_LOCK})


async def test_each_lane_claims_only_its_own_jobs():
    # 打标在长通道排着，爬虫同步在短通道照样能领到，不用等打标跑完。
    await trigger(job_code("type"))
    await trigger()
    long_claim = await runner.claim_next(LONG_LANE)
    short_claim = await runner.claim_next(SHORT_LANE)
    assert long_claim and long_claim[1] == job_code("type")
    assert short_claim and short_claim[1] == "crawler"
    assert await runner.claim_next(LONG_LANE) is None
    # 只回收一条通道时，另一条通道正在跑的不受影响。
    await runner.recover_interrupted(SHORT_LANE)
    async with SessionLocal() as session:
        assert (await session.get(ScheduledRun, short_claim[0])).status == "retrying"
        assert (await session.get(ScheduledRun, long_claim[0])).status == "running"


async def test_empty_database_refuses_automatic_backfill():
    with pytest.raises(RuntimeError, match="首次历史回填"):
        await run_crawler(uuid.uuid4())


async def test_api_authorization_validation_and_queue():
    class Authz:
        async def authorize(self, *, access_token, resource, action):
            assert resource == "system.scheduler"
            if access_token == "readonly" and action != "list":
                raise PermissionDeniedError()
            return type("Principal", (), {"user_id": ACTOR.id, "display_name": ACTOR.name})()

    app.dependency_overrides[get_authz_client] = Authz
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        base = "/api/v1/policy/scheduled-jobs"
        assert (await client.get(base)).status_code == 401
        headers = {"Authorization": "Bearer readonly"}
        assert (await client.get(base, headers=headers)).status_code == 200
        assert (await client.post(base + "/crawler/runs", headers=headers)).status_code == 403
        assert (
            await client.patch(
                base + "/crawler", headers=headers, json={"enabled": False, "daily_time": "10:00", "version": 1}
            )
        ).status_code == 403
        headers = {"Authorization": "Bearer admin"}
        assert (
            await client.patch(
                base + "/crawler", headers=headers, json={"enabled": True, "daily_time": "25:00", "version": 1}
            )
        ).status_code == 422
        assert (await client.post(base + "/arbitrary/runs", headers=headers)).status_code == 404
        assert (await client.post(base + "/crawler/runs", headers=headers)).status_code == 202
        assert (await client.post(base + "/crawler/runs", headers=headers)).status_code == 409
        assert (await client.get(base + "/crawler/runs", headers=headers)).json()["data"]["total"] == 1
