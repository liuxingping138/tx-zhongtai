"""汇总各领域的 ORM 模型：导入本模块即把全部表注册到 Base.metadata，供 Alembic 与元数据校验使用。"""

from __future__ import annotations

from app.common.models import OutboxEvent
from app.crawler.domain.models import (
    CrawlerSite,
    CrawlerSiteDaily,
    CrawlerV2SyncRun,
)
from app.policy.domain.models import BaseTag, Interpretation, Source
from app.scheduler.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat

__all__ = [
    "BaseTag",
    "CrawlerSite",
    "CrawlerSiteDaily",
    "CrawlerV2SyncRun",
    "Interpretation",
    "OutboxEvent",
    "ScheduledJob",
    "ScheduledRun",
    "SchedulerHeartbeat",
    "Source",
]
