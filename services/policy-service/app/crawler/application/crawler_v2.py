"""爬虫监测业务编排。所有数字来自本地快照，页面不触碰爬虫库。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import build_workbook_async
from platform_common.filters import Filters
from platform_common.options import preview_options, search_options
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.crawler.domain.fields import CRAWLER_SITE_COLUMNS, CRAWLER_SITE_STATUS_LABELS
from app.crawler.domain.models import CrawlerSite
from app.crawler.repositories import crawler_v2 as repo

# 日常同步每天一次，超过这个时长没有成功同步，页面提示数据可能过期。
_STALE_SYNC_AFTER = timedelta(hours=36)


def _to_out(row: CrawlerSite) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "site_name": row.site_name,
        "province_name": row.province_name,
        "city_name": row.city_name,
        "total_rows": row.total_rows,
        "last_created_at": format_beijing(row.last_created_at),
        "last_published_date": row.last_published_date.isoformat() if row.last_published_date else "",
        "stale_days": row.stale_days,
        "status": row.status,
        "status_label": CRAWLER_SITE_STATUS_LABELS.get(row.status, row.status),
    }


async def list_sites(session: AsyncSession, *, filters: Filters, page: int, page_size: int) -> dict[str, Any]:
    rows, total = await repo.list_items(session, filters=filters, page=page, page_size=page_size)
    return {"items": [_to_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


async def _sync_status(session: AsyncSession) -> dict[str, Any]:
    run = await repo.last_run(session)
    success = await repo.last_successful_run(session)
    status = run.status if run else ""
    # 进程被杀、容器重启时批次会一直停在 running；锁随连接释放，据此识别为中断。
    if status == "running" and not await repo.sync_lock_held(session):
        status = "interrupted"
    return {
        "status": status,
        "started_at": format_beijing(run.started_at) if run else "",
        "last_success_at": format_beijing(success.finished_at) if success else "",
        "outdated": bool(success and success.finished_at and utcnow() - success.finished_at > _STALE_SYNC_AFTER),
    }


async def overview(session: AsyncSession) -> dict[str, Any]:
    """卡片和同步状态一次返回，避免前端串行发多个请求。"""

    today = utcnow().astimezone(BEIJING).date()
    totals = await repo.totals(session)
    return {
        "cards": {**totals, "yesterday_rows": await repo.day_rows(session, today - timedelta(days=1))},
        "sync": await _sync_status(session),
        "thresholds": {
            "normal_days": get_settings().crawler_health_normal_days,
            "watch_days": get_settings().crawler_health_watch_days,
        },
    }


async def list_options(session: AsyncSession) -> dict[str, Any]:
    options = await preview_options(session, repo.FILTER_COLUMNS)
    options["status"] = {"items": [CRAWLER_SITE_STATUS_LABELS[s] for s in repo.STATUSES], "truncated": False}
    return {"options": options}


async def search_filter_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    return await search_options(session, repo.FILTER_COLUMNS, field=field, keyword=keyword)


async def export_sites(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    limit = get_settings().export_max_rows
    total = await repo.count_filtered(session, filters)
    if total > limit:
        raise ApiError(
            f"筛选结果共 {total} 条，超过单次导出上限 {limit} 条，请先缩小筛选范围后再导出。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    rows = [_to_out(row) for row in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="policy.crawler_monitoring_v2.exported",
        actor=actor,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(CRAWLER_SITE_COLUMNS, rows, sheet_name="爬虫监测")
