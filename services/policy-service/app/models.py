"""汇总各领域的 ORM 模型：导入本模块即把全部表注册到 Base.metadata，供 Alembic 与元数据校验使用。"""

from __future__ import annotations

from app.aitag.domain.models import PolicyAiRun, PolicyAiTask, SkippedSource
from app.common.models import OutboxEvent
from app.crawlconfig.domain.models import ConfigSyncRun
from app.crawler.domain.models import (
    CrawlerSite,
    CrawlerSiteDaily,
    CrawlerStatusDaily,
    CrawlerSyncRun,
)
from app.policy.domain.candidates import ScenarioCandidate
from app.policy.domain.models import BaseTag, Interpretation, Source
from app.scheduler.domain.models import ScheduledJob, ScheduledRun, SchedulerHeartbeat

__all__ = [
    "BaseTag",
    "ConfigSyncRun",
    "CrawlerSite",
    "CrawlerSiteDaily",
    "CrawlerStatusDaily",
    "CrawlerSyncRun",
    "Interpretation",
    "OutboxEvent",
    "PolicyAiRun",
    "PolicyAiTask",
    "ScenarioCandidate",
    "ScheduledJob",
    "ScheduledRun",
    "SchedulerHeartbeat",
    "SkippedSource",
    "Source",
]
