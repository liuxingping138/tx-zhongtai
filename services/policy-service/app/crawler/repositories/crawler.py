"""爬虫监测查询。数据源是同步任务写好的本地聚合表，不连爬虫库。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from platform_common.clock import BEIJING, utcnow
from platform_common.filters import Filters, contains_ilike, ilike_any, in_any
from sqlalchemy import ColumnElement, Date, Integer, and_, case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.crawler.domain.models import CrawlerDailyStat, CrawlerSyncRun, CrawlerTaskHealth

ABNORMAL_STATUSES = ("broken", "never")

# 列表、导出、计数共用这一份定义，杜绝导出条件和列表走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "province_name": CrawlerTaskHealth.province_name,
    "city_name": CrawlerTaskHealth.city_name,
    "site_name": CrawlerTaskHealth.site_name,
    "site_code": CrawlerTaskHealth.site_code,
    "tag": CrawlerTaskHealth.tag,
}
# 这两个不是模糊匹配：状态要精确相等，停更天数是数值下限。
EXACT_FILTERS = ("health_status",)
NUMERIC_FILTERS = ("stale_days_min",)

# v1 同步进程持有的会话级 advisory lock，与 v2 的键不同，两套同步互不阻塞。
SYNC_LOCK_KEY = 72120260922


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        if value is None or value == "" or value is False:
            continue
        if key in EXACT_FILTERS:
            status = in_any(CrawlerTaskHealth.health_status, value)
            if status is not None:
                conds.append(status)
        elif key in NUMERIC_FILTERS:
            if not isinstance(value, int | str):
                raise TypeError(f"{key} 需要整数")
            conds.append(CrawlerTaskHealth.stale_days >= int(value))
        elif key == "abnormal_only":
            conds.append(CrawlerTaskHealth.health_status.in_(ABNORMAL_STATUSES))
        else:
            column = FILTER_COLUMNS[key]  # 未知字段直接 KeyError，API 层转 422
            cond = ilike_any(column, value)
            if cond is not None:
                conds.append(cond)
    return conds


# 断爬的排最前面、停更越久越靠前，打开页面先看到要修的。
_STATUS_RANK = case(
    (CrawlerTaskHealth.health_status == "broken", 0),
    (CrawlerTaskHealth.health_status == "never", 1),
    (CrawlerTaskHealth.health_status == "watch", 2),
    else_=3,
)
_ORDER = (
    _STATUS_RANK,
    CrawlerTaskHealth.stale_days.desc().nullslast(),
    CrawlerTaskHealth.site_name,
    CrawlerTaskHealth.tag,
    CrawlerTaskHealth.site_key,
)


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[CrawlerTaskHealth], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(CrawlerTaskHealth).where(*conds)) or 0)
    result = await session.execute(
        select(CrawlerTaskHealth).where(*conds).order_by(*_ORDER).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(CrawlerTaskHealth).where(*_conditions(filters))) or 0
    )


async def list_filtered(session: AsyncSession, filters: Filters) -> list[CrawlerTaskHealth]:
    result = await session.execute(select(CrawlerTaskHealth).where(*_conditions(filters)).order_by(*_ORDER))
    return list(result.scalars())


async def health_distribution(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(CrawlerTaskHealth.health_status, func.count()).group_by(CrawlerTaskHealth.health_status)
    )
    return {status: int(count) for status, count in result.all()}


async def site_health_summary(session: AsyncSession) -> dict[str, int]:
    """站级汇总。一个站几十个标签，只有全挂才算整站失联，挂一部分单独统计。"""

    normal_tags = func.count().filter(CrawlerTaskHealth.health_status.in_(("normal", "watch")))
    abnormal_tags = func.count().filter(CrawlerTaskHealth.health_status.in_(ABNORMAL_STATUSES))
    per_site = (
        select(
            CrawlerTaskHealth.site_key.label("site_key"),
            normal_tags.label("alive"),
            abnormal_tags.label("dead"),
        )
        .group_by(CrawlerTaskHealth.site_key)
        .subquery()
    )
    result = await session.execute(
        select(
            func.count(),
            func.count().filter(and_(per_site.c.alive == 0, per_site.c.dead > 0)),
            func.count().filter(and_(per_site.c.alive > 0, per_site.c.dead > 0)),
        ).select_from(per_site)
    )
    total, all_broken, partial = result.one()
    return {"sites_total": int(total), "sites_all_broken": int(all_broken), "sites_partial_broken": int(partial)}


async def daily_trend(session: AsyncSession, days: int) -> list[dict[str, Any]]:
    """近 N 天日采集量。用 generate_series 补齐没有数据的日子，折线不会断。"""

    series = select(
        cast(
            func.generate_series(
                cast(func.timezone("Asia/Shanghai", func.now()), Date) - cast(days - 1, Integer),
                cast(func.timezone("Asia/Shanghai", func.now()), Date),
                text("'1 day'::interval"),
            ),
            Date,
        ).label("day")
    ).subquery()
    agg = (
        select(
            CrawlerDailyStat.collect_date.label("day"),
            func.sum(CrawlerDailyStat.row_count).label("rows"),
            func.count(func.distinct(CrawlerDailyStat.site_key)).label("sites"),
        )
        .where(
            CrawlerDailyStat.identity_verified,
            CrawlerDailyStat.collect_date
            > cast(func.timezone("Asia/Shanghai", func.now()), Date) - cast(days, Integer),
        )
        .group_by(CrawlerDailyStat.collect_date)
        .subquery()
    )
    result = await session.execute(
        select(series.c.day, func.coalesce(agg.c.rows, 0), func.coalesce(agg.c.sites, 0))
        .select_from(series.outerjoin(agg, agg.c.day == series.c.day))
        .order_by(series.c.day)
    )
    return [{"date": day.isoformat(), "rows": int(rows), "sites": int(sites)} for day, rows, sites in result.all()]


async def day_totals(session: AsyncSession, day: date) -> dict[str, int]:
    result = await session.execute(
        select(
            func.coalesce(func.sum(CrawlerDailyStat.row_count), 0),
            func.count(func.distinct(CrawlerDailyStat.site_key)),
            func.count(),
        ).where(CrawlerDailyStat.identity_verified, CrawlerDailyStat.collect_date == day)
    )
    rows, sites, tasks = result.one()
    return {"rows": int(rows), "sites": int(sites), "tasks": int(tasks)}


async def task_daily_series(session: AsyncSession, *, site_key: str, tag: str, days: int) -> list[dict[str, Any]]:
    today = utcnow().astimezone(BEIJING).date()
    start = today - timedelta(days=days - 1)
    result = await session.execute(
        select(CrawlerDailyStat.collect_date, CrawlerDailyStat.row_count).where(
            CrawlerDailyStat.site_key == site_key,
            CrawlerDailyStat.tag == tag,
            CrawlerDailyStat.identity_verified,
            CrawlerDailyStat.collect_date.between(start, today),
        )
    )
    counts = dict(result.tuples().all())
    return [
        {"date": (today - timedelta(days=i)).isoformat(), "rows": int(counts.get(today - timedelta(days=i), 0))}
        for i in range(days)
    ]


async def get_task(session: AsyncSession, *, site_key: str, tag: str) -> CrawlerTaskHealth | None:
    result = await session.execute(
        select(CrawlerTaskHealth).where(CrawlerTaskHealth.site_key == site_key, CrawlerTaskHealth.tag == tag)
    )
    return result.scalar_one_or_none()


async def pending_identity_backfill(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(func.count(func.distinct(CrawlerDailyStat.collect_date)), func.min(CrawlerDailyStat.collect_date)).where(
            CrawlerDailyStat.identity_verified.is_(False)
        )
    )
    count, first = result.one()
    return {"days": int(count), "since": first.isoformat() if first else ""}


async def last_successful_sync(session: AsyncSession) -> CrawlerSyncRun | None:
    result = await session.execute(
        select(CrawlerSyncRun)
        .where(CrawlerSyncRun.status == "success")
        .order_by(CrawlerSyncRun.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def last_sync(session: AsyncSession) -> CrawlerSyncRun | None:
    result = await session.execute(select(CrawlerSyncRun).order_by(CrawlerSyncRun.started_at.desc()).limit(1))
    return result.scalar_one_or_none()


async def distinct_values(session: AsyncSession, field: str, keyword: str | None, limit: int) -> list[str]:
    column = FILTER_COLUMNS[field]
    stmt = select(func.distinct(column)).where(column != "")
    if keyword:
        stmt = stmt.where(contains_ilike(column, keyword))
    result = await session.execute(stmt.order_by(column).limit(limit))
    return [value for value in result.scalars() if value]


async def has_any_data(session: AsyncSession) -> bool:
    return bool(await session.scalar(select(func.count()).select_from(CrawlerTaskHealth).limit(1)))


__all__ = [
    "ABNORMAL_STATUSES",
    "FILTER_COLUMNS",
    "count_filtered",
    "daily_trend",
    "day_totals",
    "distinct_values",
    "get_task",
    "has_any_data",
    "health_distribution",
    "last_sync",
    "list_filtered",
    "list_items",
    "site_health_summary",
    "task_daily_series",
]
