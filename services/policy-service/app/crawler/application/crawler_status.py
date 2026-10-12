"""爬虫监测状态历史（较上周对比）和单个网站的采集曲线。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crawler.application import crawler_stats as stats
from app.crawler.repositories import crawler_status as repo

# 补齐历史时最多回看这么多天；卡片只比上周，留 90 天够以后画状态走势。
HISTORY_DAYS = 90
COMPARE_DAYS = 7


async def refresh_history(session: AsyncSession, today: date) -> None:
    """同步重建快照后调用：先补齐缺的历史日期（只在首次或断档时慢），再按快照写当天。"""

    settings = get_settings()
    missing = await repo.missing_dates(session, today - timedelta(days=HISTORY_DAYS), today - timedelta(days=1))
    if missing:
        await repo.backfill(
            session,
            missing[0],
            missing[-1],
            normal_days=settings.crawler_health_normal_days,
            watch_days=settings.crawler_health_watch_days,
        )
    await repo.record_today(session, today)


async def week_base(session: AsyncSession) -> dict[str, Any] | None:
    """最新统计日往前一周的状态分布，前端据此算「较上周」；还没有那天的记录时返回 None，不显示对比。"""

    latest, base = await repo.latest_and_base(session, COMPARE_DAYS)
    if latest is None or base is None:
        return None
    return {
        "date": base.snapshot_date.isoformat(),
        "sites": base.sites,
        "normal": base.normal,
        "watch": base.watch,
        "stale": base.stale,
    }


async def site_trend(
    session: AsyncSession, *, site_name: str, province_name: str, city_name: str, days: int
) -> dict[str, Any]:
    end = stats.yesterday()
    start = end - timedelta(days=days - 1)
    rows = await repo.site_series(
        session, site_name=site_name, province_name=province_name, city_name=city_name, start=start, end=end
    )
    return {"date_from": start.isoformat(), "date_to": end.isoformat(), "items": stats.fill_series(start, end, rows)}
