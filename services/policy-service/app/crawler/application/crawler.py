"""爬虫监测业务编排。所有数字来自本地聚合表，页面不触碰爬虫库。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import build_workbook_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.crawler.domain.fields import CRAWLER_TASK_COLUMNS, HEALTH_STATUS_LABELS
from app.crawler.domain.models import CrawlerTaskHealth
from app.crawler.repositories import crawler as repo

_TREND_MAX_DAYS = 180


def _to_out(row: CrawlerTaskHealth) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "site_key": row.site_key,
        "site_code": row.site_code,
        "site_name": row.site_name,
        "province_name": row.province_name,
        "city_name": row.city_name,
        "tag": row.tag,
        "source_url": row.source_url,
        "last_collect_date": row.last_collect_date.isoformat() if row.last_collect_date else "",
        "stale_days": row.stale_days,
        "count_7d": row.count_7d,
        "count_30d": row.count_30d,
        "count_90d": row.count_90d,
        "count_total": row.count_total,
        "health_status": row.health_status,
        "health_status_label": HEALTH_STATUS_LABELS.get(row.health_status, row.health_status),
        "in_rules": row.in_rules,
        "in_rules_label": "是" if row.in_rules else "否",
        "computed_at": format_beijing(row.computed_at),
    }


async def list_tasks(session: AsyncSession, *, filters: Filters, page: int, page_size: int) -> dict[str, Any]:
    rows, total = await repo.list_items(session, filters=filters, page=page, page_size=page_size)
    return {"items": [_to_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


async def overview(session: AsyncSession, *, trend_days: int) -> dict[str, Any]:
    """页面顶部的卡片和两张图。一次查完，避免前端串行发四五个请求。"""

    today = utcnow().astimezone(BEIJING).date()
    distribution = await repo.health_distribution(session)
    sites = await repo.site_health_summary(session)
    yesterday = await repo.day_totals(session, today - timedelta(days=1))
    day_before = await repo.day_totals(session, today - timedelta(days=2))
    sync_run = await repo.last_sync(session)
    successful = await repo.last_successful_sync(session)
    backfill = await repo.pending_identity_backfill(session)

    abnormal = sum(distribution.get(status, 0) for status in repo.ABNORMAL_STATUSES)
    total_tasks = sum(distribution.values())
    return {
        "data_status": {
            "last_success_at": format_beijing(successful.finished_at) if successful else "",
            "stale": bool(
                successful and successful.finished_at and utcnow() - successful.finished_at > timedelta(hours=36)
            ),
            "pending_backfill": backfill,
        },
        "cards": {
            "yesterday_rows": yesterday["rows"],
            "yesterday_rows_delta": yesterday["rows"] - day_before["rows"],
            "yesterday_sites": yesterday["sites"],
            "total_tasks": total_tasks,
            "abnormal_tasks": abnormal,
            "healthy_ratio": round((total_tasks - abnormal) / total_tasks * 100, 1) if total_tasks else 0.0,
            "sites_total": sites["sites_total"],
            "sites_all_broken": sites["sites_all_broken"],
            "sites_partial_broken": sites["sites_partial_broken"],
        },
        "health_distribution": [
            {"status": status, "label": HEALTH_STATUS_LABELS.get(status, status), "count": distribution.get(status, 0)}
            for status in ("normal", "watch", "broken", "never")
        ],
        "trend": await repo.daily_trend(session, min(trend_days, _TREND_MAX_DAYS)),
        "last_sync": {
            "status": sync_run.status if sync_run else "",
            "started_at": format_beijing(sync_run.started_at) if sync_run else "",
            "finished_at": format_beijing(sync_run.finished_at) if sync_run and sync_run.finished_at else "",
            "date_to": sync_run.date_to.isoformat() if sync_run else "",
            "error_message": sync_run.error_message if sync_run else None,
        }
        if sync_run
        else None,
    }


async def task_detail(
    session: AsyncSession, *, site_code: str, tag: str, days: int, site_key: str | None = None
) -> dict[str, Any]:
    key = site_key or (f"code:{site_code.strip()}" if site_code.strip() else "")
    if not key:
        raise ApiError("缺少网站标识，请刷新列表后重试", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    row = await repo.get_task(session, site_key=key, tag=tag)
    if row is None:
        raise ApiError("任务不存在", code=ErrorCode.RESOURCE_NOT_FOUND, http_status=404)
    return {
        "task": _to_out(row),
        "series": await repo.task_daily_series(session, site_key=key, tag=tag, days=min(days, _TREND_MAX_DAYS)),
    }


async def list_options(session: AsyncSession) -> dict[str, Any]:
    from platform_common.options import PREVIEW_LIMIT

    items: dict[str, Any] = {}
    for field in repo.FILTER_COLUMNS:
        values = await repo.distinct_values(session, field, None, PREVIEW_LIMIT + 1)
        items[field] = {
            "items": values[:PREVIEW_LIMIT],
            "truncated": len(values) > PREVIEW_LIMIT,
        }
    items["health_status"] = {
        "items": [HEALTH_STATUS_LABELS[status] for status in ("normal", "watch", "broken", "never")],
        "truncated": False,
    }
    return {"options": items}


async def search_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    from platform_common.options import SEARCH_LIMIT

    return await repo.distinct_values(session, field, keyword, SEARCH_LIMIT)


async def export_tasks(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
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
        event_type="policy.crawler_monitoring.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows), "abnormal_only": bool(filters.get("abnormal_only"))},
    )
    sheet = "爬虫异常清单" if filters.get("abnormal_only") else "爬虫监测"
    return await build_workbook_async(CRAWLER_TASK_COLUMNS, rows, sheet_name=sheet)
