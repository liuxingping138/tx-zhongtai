"""爬虫监测 v2 查询。页面只读网站快照表，昨日采集量读按天统计，都不连爬虫库。"""

from __future__ import annotations

from datetime import date

from platform_common.filters import Filters, ilike_any, in_any
from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.crawler.domain.models import CrawlerSite, CrawlerSiteDaily, CrawlerV2SyncRun

STATUSES = ("normal", "watch", "stale")
# 同步进程持有的会话级 advisory lock。取 2^31 以内，pg_locks 里 classid=0、objid 就是它。
SYNC_LOCK_KEY = 20260923

# 列表、导出、计数共用这一份定义，杜绝导出条件和列表走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "province_name": CrawlerSite.province_name,
    "city_name": CrawlerSite.city_name,
    "site_name": CrawlerSite.site_name,
}
# 状态是精确匹配，不在模糊匹配的 FILTER_COLUMNS 里。
EXACT_FILTERS = ("status",)


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        if key in EXACT_FILTERS:
            cond = in_any(CrawlerSite.status, value)
        else:
            column = FILTER_COLUMNS[key]  # 未知字段直接 KeyError，API 层转 422
            cond = ilike_any(column, value)
        if cond is not None:
            conds.append(cond)
    return conds


# 停更天数少的排前面：默认先看到正常出数的网站；按「停更」筛选时，刚停更、最值得马上排查的
# 排在最前，停了几年的老站排到最后（2026-09-23 用户确认，原先按停更天数倒序会让上千个老站占满前几十页）。
_ORDER = (
    CrawlerSite.stale_days.asc().nullslast(),
    CrawlerSite.total_rows.desc(),
    CrawlerSite.site_name,
    CrawlerSite.province_name,
    CrawlerSite.city_name,
)


async def list_items(
    session: AsyncSession, *, filters: Filters, page: int, page_size: int
) -> tuple[list[CrawlerSite], int]:
    total = await count_filtered(session, filters)
    result = await session.execute(
        select(CrawlerSite)
        .where(*_conditions(filters))
        .order_by(*_ORDER)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    return int(await session.scalar(select(func.count()).select_from(CrawlerSite).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[CrawlerSite]:
    result = await session.execute(select(CrawlerSite).where(*_conditions(filters)).order_by(*_ORDER))
    return list(result.scalars())


def _status_count(status: str) -> ColumnElement[int]:
    return func.count().filter(CrawlerSite.status == status)


async def totals(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(
            func.count(),
            _status_count("normal"),
            _status_count("watch"),
            _status_count("stale"),
            func.coalesce(func.sum(CrawlerSite.total_rows), 0),
        )
    )
    sites, normal, watch, stale, rows = result.one()
    return {"sites": sites, "normal": normal, "watch": watch, "stale": stale, "total_rows": int(rows)}


async def day_rows(session: AsyncSession, day: date) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(CrawlerSiteDaily.row_count), 0)).where(CrawlerSiteDaily.collect_date == day)
        )
        or 0
    )


async def last_run(session: AsyncSession) -> CrawlerV2SyncRun | None:
    run: CrawlerV2SyncRun | None = await session.scalar(
        select(CrawlerV2SyncRun).order_by(CrawlerV2SyncRun.started_at.desc()).limit(1)
    )
    return run


async def last_successful_run(session: AsyncSession) -> CrawlerV2SyncRun | None:
    run: CrawlerV2SyncRun | None = await session.scalar(
        select(CrawlerV2SyncRun)
        .where(CrawlerV2SyncRun.status == "success")
        .order_by(CrawlerV2SyncRun.started_at.desc())
        .limit(1)
    )
    return run


async def sync_lock_held(session: AsyncSession) -> bool:
    """同步进程持有会话级 advisory lock；进程被杀或容器重启时锁随连接释放。"""

    return bool(
        await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid = 0 AND objid = :key AND objsubid = 1 AND granted)"
            ),
            {"key": SYNC_LOCK_KEY},
        )
    )
