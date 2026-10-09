"""只在显式指定的全新 scheduler_test 库运行，不接真实爬虫源。"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

import httpx
import pytest
import pytest_asyncio
from platform_common.actors import Actor
from platform_common.errors import PermissionDeniedError, VersionConflictError
from sqlalchemy import delete, text

from app.api.security import get_authz_client
from app.application import scheduler as service
from app.core.database import SessionLocal, engine
from app.domain.models import CrawlerV2SyncRun
from app.domain.scheduler_models import ScheduledRun
from app.domain.scheduling import LEADER_LOCK
from app.main import app
from app.repositories import scheduler as repo
from app.worker import scheduler as worker

pytestmark = pytest.mark.skipif(os.environ.get("SCHEDULER_INTEGRATION") != "1", reason="需要独立 scheduler_test 数据库")
ACTOR = Actor(id=str(uuid.uuid4()), name="调度验收")


@pytest_asyncio.fixture(autouse=True)
async def isolated():
    assert engine.url.database == "scheduler_test", "拒绝在业务数据库执行破坏性测试"
    async with SessionLocal() as session:
        await session.execute(delete(ScheduledRun))
        await session.execute(delete(CrawlerV2SyncRun))
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


async def trigger(code="crawler-v2"):
    async with SessionLocal() as session:
        row = await service.trigger_job(session, code, ACTOR)
        await session.commit()
        return row


async def test_parallel_manual_requests_coalesce():
    results = await asyncio.gather(trigger(), trigger(), return_exceptions=True)
    assert sum(isinstance(x, dict) for x in results) == 1
    assert sum(isinstance(x, VersionConflictError) for x in results) == 1
    async with SessionLocal() as session:
        assert len((await repo.history(session, "crawler-v2", 1, 20))[0]) == 1


async def test_missed_days_catch_up_once_and_manual_race():
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        job = await repo.get_job(session, "crawler-v2", lock=True)
        job.next_run_at = now - timedelta(days=4)
        await session.commit()

    async def schedule():
        async with SessionLocal() as session:
            await repo.schedule_due(session, now)
            await session.commit()

    results = await asyncio.gather(schedule(), trigger(), return_exceptions=True)
    assert all(x is None or isinstance(x, (dict, VersionConflictError)) for x in results)
    await schedule()
    async with SessionLocal() as session:
        rows, total = await repo.history(session, "crawler-v2", 1, 20)
        assert total == 1 and rows[0].status == "queued"
        assert (await repo.get_job(session, "crawler-v2")).next_run_at > now


async def test_pause_cancels_pending_and_version_conflict():
    await trigger()
    async with SessionLocal() as session:
        await service.update_job(session, "crawler-v2", ACTOR, enabled=False, daily_time="11:00", version=1)
        await session.commit()
        assert (await repo.history(session, "crawler-v2", 1, 20))[0][0].status == "cancelled"
    async with SessionLocal() as session:
        with pytest.raises(VersionConflictError):
            await service.update_job(session, "crawler-v2", ACTOR, enabled=True, daily_time="12:00", version=1)
    # 停用计划后仍允许一次手动执行。
    assert (await trigger())["status"] == "queued"


async def test_failure_retry_success_and_saved_result(monkeypatch):
    await trigger()
    claim = await worker.claim_next()
    assert claim
    monkeypatch.setattr(worker, "execute_sync", AsyncMock(side_effect=ValueError("secret")))
    await worker.execute_claim(claim)
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "retrying" and row.attempts == 1 and "secret" not in row.error_message
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    next_claim = await worker.claim_next()
    assert next_claim and next_claim[2] != claim[2]

    async def success(code, sync_id):
        async with SessionLocal() as session:
            session.add(
                CrawlerV2SyncRun(
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

    monkeypatch.setattr(worker, "execute_sync", success)
    await worker.execute_claim(next_claim)
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "success" and row.attempts == 2 and row.error_message is None
        assert row.result["site_rows"] == 12


async def test_recovery_does_not_repeat_completed_sync():
    await trigger()
    claim = await worker.claim_next()
    async with SessionLocal() as session:
        session.add(
            CrawlerV2SyncRun(
                id=claim[2],
                mode="incremental",
                started_at=datetime.now(UTC),
                status="success",
                days_synced=1,
                site_rows=4,
            )
        )
        await session.commit()
    await worker.recover_interrupted()
    async with SessionLocal() as session:
        row = await session.get(ScheduledRun, claim[0])
        assert row.status == "success" and row.result["site_rows"] == 4
    assert await worker.claim_next() is None


async def test_timeout_closes_running_sync_batch(monkeypatch):
    await trigger()
    claim = await worker.claim_next()
    assert claim

    # 先持久化已运行批次，再测试超时清理；不能假设远端 DB 在 50ms 内提交。
    async with SessionLocal() as session:
        session.add(
            CrawlerV2SyncRun(
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

    monkeypatch.setattr(worker, "execute_sync", hang)
    monkeypatch.setattr(worker, "TIMEOUT_SECONDS", 0.05)
    await worker.execute_claim(claim)
    async with SessionLocal() as session:
        scheduled = await session.get(ScheduledRun, claim[0])
        sync = await session.get(CrawlerV2SyncRun, claim[2])
        assert scheduled is not None and scheduled.status == "retrying"
        assert sync is not None and sync.status == "failed"
        assert sync.error_message


async def test_recovery_retries_interrupted_run_and_global_lock():
    await trigger()
    claim = await worker.claim_next()
    await worker.recover_interrupted()
    async with SessionLocal() as session:
        assert (await session.get(ScheduledRun, claim[0])).status == "retrying"
    async with engine.connect() as first, engine.connect() as second:
        assert await first.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK})
        try:
            assert not await second.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK})
        finally:
            await first.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_LOCK})


async def test_empty_database_refuses_automatic_backfill():
    with pytest.raises(RuntimeError, match="首次历史回填"):
        await worker.execute_sync("crawler-v2", uuid.uuid4())
    with pytest.raises(RuntimeError, match="首次历史回填"):
        await worker.execute_sync("crawler-v1", uuid.uuid4())


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
        assert (await client.post(base + "/crawler-v2/runs", headers=headers)).status_code == 403
        assert (
            await client.patch(
                base + "/crawler-v2", headers=headers, json={"enabled": False, "daily_time": "10:00", "version": 1}
            )
        ).status_code == 403
        headers = {"Authorization": "Bearer admin"}
        assert (
            await client.patch(
                base + "/crawler-v2", headers=headers, json={"enabled": True, "daily_time": "25:00", "version": 1}
            )
        ).status_code == 422
        assert (await client.post(base + "/arbitrary/runs", headers=headers)).status_code == 404
        assert (await client.post(base + "/crawler-v2/runs", headers=headers)).status_code == 202
        assert (await client.post(base + "/crawler-v2/runs", headers=headers)).status_code == 409
        assert (await client.get(base + "/crawler-v2/runs", headers=headers)).json()["data"]["total"] == 1
