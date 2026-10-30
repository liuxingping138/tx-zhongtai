"""爬虫配置同步：规则表里出现的网站编码，对应信源标成已爬，上线时间 = 这个网站最早那条规则的创建日期。

爬虫同事每周批量建规则，创建日期就是真实的配置日：按它统计每周配置数量和用户按规则表透视的结果一致，
同步哪天漏跑、重跑几次都不会让网站换周。已爬的上线时间也对齐成创建日期；异常是人工标的不动，
网站从规则表里消失也不改回去。调度任务 crawler_config 每天跑，统计页可以手动触发；失败、超时由调度收口。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crawlconfig.application import expand
from app.crawlconfig.domain.models import ConfigSyncRun
from app.crawlconfig.repositories import rules_source, sources

logger = logging.getLogger("policy.crawler_config")
ROBOT = Actor(id="crawler-config-sync", name="爬虫配置同步")
# 审计里最多记这么多个网站编码。
AUDIT_CODES_MAX = 500
SUMMARY_FIELDS = (
    "status",
    "rule_rows",
    "rule_codes",
    "blank_code_rows",
    "matched",
    "marked",
    "redated",
    "unknown_codes",
    "added",
)


async def run(sync_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        session.add(ConfigSyncRun(id=sync_id, status="running", started_at=utcnow()))
        await session.commit()
    settings = get_settings()
    rules = await asyncio.to_thread(rules_source.read_rule_codes, settings.crawler_config_expand_from)
    async with SessionLocal() as session:
        now = utcnow()
        # 先按栏目展开新规则（展开过的行记了规则 ID，下面按网站一行的对齐不再碰它们）。
        expanded = await expand.expand(session, rules.columns, set(rules.first_dates), now=now, actor=ROBOT)
        if expanded.conflicts:
            logger.warning("crawler_config_expand_conflicts count=%s", len(expanded.conflicts))
        if expanded.plan.duplicates:
            logger.info("crawler_config_same_page_skipped count=%s", len(expanded.plan.duplicates))
        placeholder = settings.crawler_config_backfill_date.isoformat()
        marked, redated = await sources.apply_rule_dates(
            session, rules.first_dates, now=now, actor=ROBOT, placeholder=placeholder
        )
        marked, redated = [*marked, *expanded.marked], [*redated, *expanded.redated]
        matched = await sources.count_known(session, rules.codes)
        row = await session.get(ConfigSyncRun, sync_id, with_for_update=True)
        if row is None:
            raise RuntimeError("同步批次记录丢失")
        row.status, row.finished_at = "success", now
        row.rule_rows, row.rule_codes, row.blank_code_rows = rules.rows, len(rules.codes), rules.blank_rows
        row.matched, row.marked, row.redated = matched, len(marked), len(redated)
        row.unknown_codes, row.added = len(rules.codes) - matched, expanded.added
        if marked or redated or expanded.added:
            await enqueue_event(
                session,
                event_type="policy.crawler_config.synced",
                actor=ROBOT,
                target_id="batch",
                changes={
                    "crawler_status": "已爬",
                    "marked": len(marked),
                    "redated": len(redated),
                    "added": expanded.added,
                },
                extra={
                    "marked_codes": marked[:AUDIT_CODES_MAX],
                    "redated_codes": redated[:AUDIT_CODES_MAX],
                    "expand_conflicts": [step.rule.rule_id for step, _ in expanded.conflicts][:AUDIT_CODES_MAX],
                },
            )
        await session.commit()


async def abandon(session: AsyncSession, sync_id: uuid.UUID, message: str) -> None:
    """超时或进程中断时把停在 running 的批次收成失败，和调度执行记录在同一个事务里提交。"""

    row = await session.get(ConfigSyncRun, sync_id)
    if row is not None and row.status == "running":
        row.status, row.error_message, row.finished_at = "failed", message[:2000], utcnow()


def _summary(row: ConfigSyncRun) -> dict[str, Any]:
    return {key: getattr(row, key) for key in SUMMARY_FIELDS}


async def summary(session: AsyncSession, sync_id: uuid.UUID | None) -> dict[str, Any] | None:
    row = await session.get(ConfigSyncRun, sync_id) if sync_id else None
    return _summary(row) if row else None


async def latest(session: AsyncSession) -> dict[str, Any] | None:
    """最近一次成功的同步：统计页顶部显示「数据截至」。"""

    row = await session.scalar(
        select(ConfigSyncRun)
        .where(ConfigSyncRun.status == "success")
        .order_by(ConfigSyncRun.started_at.desc())
        .limit(1)
    )
    return {**_summary(row), "finished_at": row.finished_at} if row else None
