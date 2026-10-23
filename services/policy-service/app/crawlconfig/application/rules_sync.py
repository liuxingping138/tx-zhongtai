"""爬虫配置同步：规则表里出现的网站编码，对应信源从未爬改成已爬，上线时间记同步当天（北京日期）。

只做这一个方向：已爬、异常的不动（异常是人工标的），网站从规则表里消失也不改回去。
调度任务 crawler_config 每天跑一次，统计页可以手动触发；失败、超时由调度收口（abandon）。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.database import SessionLocal
from app.crawlconfig.domain.models import ConfigSyncRun
from app.crawlconfig.repositories import rules_source, sources

ROBOT = Actor(id="crawler-config-sync", name="爬虫配置同步")
# 审计里最多记这么多个网站编码。
AUDIT_CODES_MAX = 500
SUMMARY_FIELDS = ("status", "rule_rows", "rule_codes", "blank_code_rows", "matched", "marked", "unknown_codes")


async def run(sync_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        session.add(ConfigSyncRun(id=sync_id, status="running", started_at=utcnow()))
        await session.commit()
    rules = await asyncio.to_thread(rules_source.read_rule_codes)
    async with SessionLocal() as session:
        now = utcnow()
        marked = await sources.mark_online(
            session, rules.codes, today=datetime.now(BEIJING).date().isoformat(), now=now, actor=ROBOT
        )
        matched = await sources.count_known(session, rules.codes)
        row = await session.get(ConfigSyncRun, sync_id, with_for_update=True)
        if row is None:
            raise RuntimeError("同步批次记录丢失")
        row.status, row.finished_at = "success", now
        row.rule_rows, row.rule_codes, row.blank_code_rows = rules.rows, len(rules.codes), rules.blank_rows
        row.matched, row.marked, row.unknown_codes = matched, len(marked), len(rules.codes) - matched
        if marked:
            await enqueue_event(
                session,
                event_type="policy.crawler_config.synced",
                actor=ROBOT,
                target_id="batch",
                changes={"crawler_status": "已爬", "rows": len(marked)},
                extra={"site_codes": marked[:AUDIT_CODES_MAX]},
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
