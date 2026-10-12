"""爬虫监测状态历史（较上周对比）、需关注清单和单个网站的采集曲线。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from platform_common.clock import format_beijing
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crawler.application import crawler_stats as stats
from app.crawler.repositories import crawler_status as repo

# 补齐历史时最多回看这么多天；卡片只比上周，留 90 天够以后画状态走势。
HISTORY_DAYS = 90
COMPARE_DAYS = 7
NEW_STALE_WITHIN_DAYS = 7
ATTENTION_LIMIT = 20
# 近 7 天不到前 4 周周均的 20%（再按整体降幅折算）算骤降；前 4 周不足 40 条的网站本来就零星，不参与。
DROP_RATIO = 0.2
DROP_BASE_WEEKS = 4
DROP_MIN_BASE_ROWS = 40


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


def _site_out(row: Any) -> dict[str, Any]:
    return {
        "site_name": row.site_name,
        "province_name": row.province_name,
        "city_name": row.city_name,
        "total_rows": row.total_rows,
        "last_created_at": format_beijing(row.last_created_at),
        "stale_days": row.stale_days,
        "status": row.status,
    }


def find_drops(rows: list[Any]) -> tuple[list[dict[str, Any]], float]:
    """按整体降幅折算后判定骤降：节假日全网都少采，不能让所有网站都上榜。"""

    total_recent = sum(row.recent for row in rows)
    total_base = sum(row.base for row in rows)
    overall = min(total_recent / (total_base / DROP_BASE_WEEKS), 1.0) if total_base else 1.0
    flagged = []
    for row in rows:
        if row.base < DROP_MIN_BASE_ROWS:
            continue
        weekly = row.base / DROP_BASE_WEEKS
        ratio = row.recent / weekly
        if ratio <= DROP_RATIO * overall:
            flagged.append(
                {
                    **_site_out(row),
                    "recent_rows": row.recent,
                    "weekly_avg": round(weekly),
                    "drop_rate": round(1 - ratio, 3),
                }
            )
    flagged.sort(key=lambda item: (-item["weekly_avg"], item["site_name"]))
    return flagged, round(overall, 3)


async def attention(session: AsyncSession) -> dict[str, Any]:
    watch_days = get_settings().crawler_health_watch_days
    new_rows, new_total = await repo.new_stale(
        session, watch_days=watch_days, within_days=NEW_STALE_WITHIN_DAYS, limit=ATTENTION_LIMIT
    )
    end = stats.yesterday()
    recent_start = end - timedelta(days=COMPARE_DAYS - 1)
    base_start = recent_start - timedelta(weeks=DROP_BASE_WEEKS)
    dropped, overall = find_drops(
        await repo.window_rows(session, base_start=base_start, recent_start=recent_start, end=end)
    )
    return {
        "new_stale": {"total": new_total, "items": [_site_out(row) for row in new_rows]},
        "dropped": {"total": len(dropped), "items": dropped[:ATTENTION_LIMIT], "overall_ratio": overall},
        "rules": {
            "new_stale_from": watch_days + 1,
            "new_stale_to": watch_days + NEW_STALE_WITHIN_DAYS,
            "drop_percent": round((1 - DROP_RATIO) * 100),
            "drop_base_weeks": DROP_BASE_WEEKS,
            "date_to": end.isoformat(),
        },
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
