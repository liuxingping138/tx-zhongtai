"""政策服务登记的定时任务：爬虫监测增量同步、爬虫配置同步、政策 AI 打标的三个任务。

调度引擎在 platform_common.scheduler；这里只把各领域 application 的入口包成 Job。
页面按这里的顺序列出任务。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from platform_common.scheduler import Job, Scheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application import tagging
from app.aitag.domain.tasks import TASKS, job_code
from app.common.audit_emit import enqueue_event
from app.core.database import SessionLocal
from app.crawlconfig.application import rules_sync
from app.crawler.application.crawler_sync import run as run_crawler_sync
from app.crawler.domain.models import CrawlerSyncRun
from app.scheduler.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat
from app.scheduler.domain.scheduling import CRAWLER, CRAWLER_CONFIG

NO_WATERMARK = "尚未建立同步水位，请先完成首次历史回填，再执行增量同步"


async def crawler_watermark(session: AsyncSession) -> datetime | None:
    """爬虫增量的成功水位。"""

    watermark: datetime | None = await session.scalar(
        select(CrawlerSyncRun.watermark)
        .where(CrawlerSyncRun.status == "success", CrawlerSyncRun.watermark.is_not(None))
        .order_by(CrawlerSyncRun.started_at.desc())
        .limit(1)
    )
    return watermark


async def run_crawler(sync_id: uuid.UUID) -> None:
    # 空库不自动跑短窗口、也不自动全量回填，要求已有成功水位。
    async with SessionLocal() as session:
        if await crawler_watermark(session) is None:
            raise RuntimeError(NO_WATERMARK)
    await run_crawler_sync(mode="incremental", run_id=sync_id)


async def abandon_crawler(session: AsyncSession, sync_id: uuid.UUID, message: str) -> None:
    sync = await session.get(CrawlerSyncRun, sync_id)
    if sync is None or sync.status != "running":
        return
    sync.status = "failed"
    sync.error_message = message[:2000]
    sync.finished_at = datetime.now(UTC)


async def crawler_summary(session: AsyncSession, sync_id: uuid.UUID) -> dict[str, Any] | None:
    sync = await session.get(CrawlerSyncRun, sync_id)
    if sync is None:
        return None
    fields = ["date_from", "date_to", "watermark", "status", "days_synced", "site_rows"]
    return {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key in fields
        if (value := getattr(sync, key)) is not None
    }


def tagging_job(task: str, name: str) -> Job:
    async def execute(run_id: uuid.UUID) -> None:
        await tagging.run_batch(run_id, task)

    # 打标批次在自己的会话里收尾和读摘要（还要停掉 ai-service 那边的任务），不用调度的会话。
    async def abandon(_session: AsyncSession, run_id: uuid.UUID, message: str) -> None:
        await tagging.abandon(run_id, message)

    async def summary(_session: AsyncSession, run_id: uuid.UUID) -> dict[str, Any] | None:
        return await tagging.summary(run_id)

    # AI 打标一批要等模型逐条回答，上千条要一两个小时。
    return Job(job_code(task), name, execute, 6 * 3600, abandon, summary)


JOBS: list[Job] = [
    Job(
        CRAWLER,
        "爬虫监测增量同步",
        run_crawler,
        timeout_seconds=1800,
        abandon=abandon_crawler,
        summary=crawler_summary,
        watermark=crawler_watermark,
        public_errors=("尚未建立同步水位", "已有爬虫"),
    ),
    # 配置同步只读规则表一列，几秒。
    Job(CRAWLER_CONFIG, "爬虫配置同步", rules_sync.run, 600, rules_sync.abandon, rules_sync.summary),
    *(tagging_job(task, name) for task, name in TASKS.items()),
]

scheduler = Scheduler(
    jobs=JOBS,
    job_model=ScheduledJob,
    run_model=ScheduledRun,
    heartbeat_model=SchedulerHeartbeat,
    audit=enqueue_event,
)
