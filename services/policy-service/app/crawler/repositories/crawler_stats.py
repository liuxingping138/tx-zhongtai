"""爬虫监测图表查询：趋势读按天统计（主键以采集日开头，按日期范围扫描），结构和省份读网站快照。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.domain.models import CrawlerSite, CrawlerSiteDaily


async def daily_series(session: AsyncSession, start: date, end: date) -> list[tuple[date, int, int]]:
    """每个采集日的数据条数与出数网站数，没有数据的日期不返回。"""

    result = await session.execute(
        select(CrawlerSiteDaily.collect_date, func.sum(CrawlerSiteDaily.row_count), func.count())
        .where(CrawlerSiteDaily.collect_date.between(start, end))
        .group_by(CrawlerSiteDaily.collect_date)
        .order_by(CrawlerSiteDaily.collect_date)
    )
    return [(day, int(rows), int(sites)) for day, rows, sites in result.all()]


async def range_rows(session: AsyncSession, start: date, end: date) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(CrawlerSiteDaily.row_count), 0)).where(
                CrawlerSiteDaily.collect_date.between(start, end)
            )
        )
        or 0
    )


async def health_buckets(session: AsyncSession, long_stale_days: int) -> dict[str, int]:
    """把停更再分成「近期停更」和「长期停更」：后者多半是网站下线或改版，处理方式不同。"""

    bucket = case(
        (CrawlerSite.status != "stale", CrawlerSite.status),
        (CrawlerSite.stale_days <= long_stale_days, "stale_recent"),
        else_="stale_long",
    )
    result = await session.execute(select(bucket, func.count()).group_by(bucket))
    counts = {"normal": 0, "watch": 0, "stale_recent": 0, "stale_long": 0}
    counts.update({str(key): int(count) for key, count in result.all()})
    return counts


async def province_status(session: AsyncSession) -> list[tuple[str, int, int, int]]:
    """按原始省份值统计正常 / 关注 / 停更网站数，归并在业务层做。"""

    result = await session.execute(
        select(
            CrawlerSite.province_name,
            func.count().filter(CrawlerSite.status == "normal"),
            func.count().filter(CrawlerSite.status == "watch"),
            func.count().filter(CrawlerSite.status == "stale"),
        ).group_by(CrawlerSite.province_name)
    )
    return [(name, int(normal), int(watch), int(stale)) for name, normal, watch, stale in result.all()]
