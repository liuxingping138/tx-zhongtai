"""爬虫监测图表数据：采集趋势、健康结构、省份分布。统计截至昨日，当天还在采集，算进来会显得骤降。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from platform_common.clock import BEIJING, utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.domain.provinces import chart_province
from app.crawler.repositories import crawler_stats as repo

# 超过这么多天没有新数据，多半是网站下线或改版，与近期停更分开统计。
LONG_STALE_DAYS = 90
# 采集量有明显的周末和节假日波动，比「昨日」要按整周比。
RECENT_DAYS = 7
TREND_DAYS = (30, 90, 365)


def _yesterday() -> date:
    return utcnow().astimezone(BEIJING).date() - timedelta(days=1)


async def recent_rows(session: AsyncSession) -> dict[str, int]:
    end = _yesterday()
    window = timedelta(days=RECENT_DAYS)
    return {
        "days": RECENT_DAYS,
        "rows": await repo.range_rows(session, end - window + timedelta(days=1), end),
        "previous_rows": await repo.range_rows(session, end - 2 * window + timedelta(days=1), end - window),
    }


async def health(session: AsyncSession) -> dict[str, int]:
    return {**await repo.health_buckets(session, LONG_STALE_DAYS), "long_stale_days": LONG_STALE_DAYS}


def merge_provinces(rows: list[tuple[str, int, int, int]]) -> list[dict[str, Any]]:
    """同一省份的不同写法合成一条，`raw_names` 留给前端点击后按原始值筛选表格。"""

    merged: dict[str, dict[str, Any]] = defaultdict(lambda: {"raw_names": [], "normal": 0, "watch": 0, "stale": 0})
    for raw, normal, watch, stale in rows:
        item = merged[chart_province(raw)]
        item["raw_names"].append(raw)
        item["normal"] += normal
        item["watch"] += watch
        item["stale"] += stale
    items = [
        {
            "name": name,
            **item,
            "raw_names": sorted(item["raw_names"]),
            "sites": item["normal"] + item["watch"] + item["stale"],
        }
        for name, item in merged.items()
    ]
    return sorted(items, key=lambda item: (-item["stale"], -item["sites"], item["name"]))


async def provinces(session: AsyncSession) -> list[dict[str, Any]]:
    return merge_provinces(await repo.province_status(session))


def fill_series(start: date, end: date, rows: list[tuple[date, int, int]]) -> list[dict[str, Any]]:
    """没有数据的日期补 0，否则图上会把相邻两天直接连起来，看不出断采。"""

    by_day = {day: (count, sites) for day, count, sites in rows}
    days = (end - start).days + 1
    items = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        count, sites = by_day.get(day, (0, 0))
        items.append({"date": day.isoformat(), "rows": count, "sites": sites})
    return items


async def trend(session: AsyncSession, days: int) -> dict[str, Any]:
    end = _yesterday()
    start = end - timedelta(days=days - 1)
    rows = await repo.daily_series(session, start, end)
    return {"date_from": start.isoformat(), "date_to": end.isoformat(), "items": fill_series(start, end, rows)}
