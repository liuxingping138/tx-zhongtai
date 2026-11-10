"""爬虫监测状态历史与单站曲线。都只读写本服务的表，不连爬虫库。"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.domain.models import CrawlerSiteDaily, CrawlerStatusDaily

# 某天的状态 = 那天回看每个网站最后一次入库的日期，口径与 crawler_sync._REBUILD_SITES 一致：
# 入库日期取 last_created_at 的北京时间日期，没有时用采集日。按网站把入库日期排成区间，一次算出整段日期。
_BACKFILL = text(
    """
    WITH act AS (
        SELECT DISTINCT site_name, province_name, city_name,
               COALESCE(CAST(last_created_at AT TIME ZONE 'Asia/Shanghai' AS date), collect_date) AS active_date
        FROM policy_crawler_site_daily
    ),
    spans AS (
        SELECT active_date,
               LEAD(active_date) OVER (
                   PARTITION BY site_name, province_name, city_name ORDER BY active_date
               ) AS next_date
        FROM act
    ),
    days AS (
        SELECT CAST(g AS date) AS d FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') g
    )
    INSERT INTO policy_crawler_status_daily (snapshot_date, sites, normal, watch, stale, computed_at)
    SELECT d, COUNT(spans.active_date),
           COUNT(spans.active_date) FILTER (WHERE d - active_date <= :normal_days),
           COUNT(spans.active_date) FILTER (WHERE d - active_date > :normal_days AND d - active_date <= :watch_days),
           COUNT(spans.active_date) FILTER (WHERE d - active_date > :watch_days),
           now()
    FROM days LEFT JOIN spans ON spans.active_date <= d AND (spans.next_date IS NULL OR spans.next_date > d)
    GROUP BY d
    ON CONFLICT (snapshot_date) DO UPDATE SET
        sites = EXCLUDED.sites, normal = EXCLUDED.normal, watch = EXCLUDED.watch,
        stale = EXCLUDED.stale, computed_at = EXCLUDED.computed_at
    """
)

_RECORD_TODAY = text(
    """
    INSERT INTO policy_crawler_status_daily (snapshot_date, sites, normal, watch, stale, computed_at)
    SELECT :day, COUNT(*),
           COUNT(*) FILTER (WHERE status = 'normal'),
           COUNT(*) FILTER (WHERE status = 'watch'),
           COUNT(*) FILTER (WHERE status = 'stale'),
           now()
    FROM policy_crawler_sites
    ON CONFLICT (snapshot_date) DO UPDATE SET
        sites = EXCLUDED.sites, normal = EXCLUDED.normal, watch = EXCLUDED.watch,
        stale = EXCLUDED.stale, computed_at = EXCLUDED.computed_at
    """
)


async def missing_dates(session: AsyncSession, start: date, end: date) -> list[date]:
    result = await session.execute(
        text(
            "SELECT CAST(g AS date) FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') g "
            "WHERE NOT EXISTS (SELECT 1 FROM policy_crawler_status_daily s WHERE s.snapshot_date = CAST(g AS date)) "
            "ORDER BY 1"
        ),
        {"start": start, "end": end},
    )
    return list(result.scalars())


async def backfill(session: AsyncSession, start: date, end: date, *, normal_days: int, watch_days: int) -> None:
    await session.execute(_BACKFILL, {"start": start, "end": end, "normal_days": normal_days, "watch_days": watch_days})


async def record_today(session: AsyncSession, day: date) -> None:
    await session.execute(_RECORD_TODAY, {"day": day})


async def latest_and_base(
    session: AsyncSession, days_back: int
) -> tuple[CrawlerStatusDaily | None, CrawlerStatusDaily | None]:
    """最新一天和它往前 days_back 天的那一行；任一缺失返回 None。"""

    latest: CrawlerStatusDaily | None = await session.scalar(
        select(CrawlerStatusDaily).order_by(CrawlerStatusDaily.snapshot_date.desc()).limit(1)
    )
    if latest is None:
        return None, None
    base = await session.get(CrawlerStatusDaily, latest.snapshot_date - timedelta(days=days_back))
    return latest, base


async def site_series(
    session: AsyncSession, *, site_name: str, province_name: str, city_name: str, start: date, end: date
) -> list[tuple[date, int, int]]:
    daily = CrawlerSiteDaily
    result = await session.execute(
        select(daily.collect_date, daily.row_count)
        .where(
            daily.collect_date.between(start, end),
            daily.site_name == site_name,
            daily.province_name == province_name,
            daily.city_name == city_name,
        )
        .order_by(daily.collect_date)
    )
    return [(day, int(rows), 1) for day, rows in result.all()]
