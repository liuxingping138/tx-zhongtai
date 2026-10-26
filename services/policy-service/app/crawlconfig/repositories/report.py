"""爬虫配置统计的查询。全部读信源表，两万来行的分组统计是毫秒级，不建快照表。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.domain.fields import CRAWLER_STATUS_ABNORMAL, CRAWLER_STATUS_ONLINE, CRAWLER_STATUS_PENDING
from app.policy.domain.models import Source

_DETAIL_ORDER = (Source.province_code, Source.province_name, Source.city_code, Source.site_code)


def online_between(date_from: str, date_to: str, backfill: str) -> ColumnElement[bool]:
    """上线时间落在 [date_from, date_to]（YYYY-MM-DD 文本按字符串比较），统一补填日（backfill）的不算。"""

    return and_(
        Source.online_date != "",
        Source.online_date != backfill,
        Source.online_date >= date_from,
        Source.online_date <= date_to,
    )


async def province_rows(session: AsyncSession, new_from: str, new_to: str, backfill: str) -> list[dict[str, Any]]:
    status = Source.crawler_status
    stmt = select(
        Source.province_name,
        func.min(func.nullif(Source.province_code, "")).label("province_code"),
        func.count().label("total"),
        func.count().filter(status == CRAWLER_STATUS_ONLINE).label("online"),
        func.count().filter(status.in_(CRAWLER_STATUS_PENDING)).label("pending"),
        func.count().filter(status == CRAWLER_STATUS_ABNORMAL).label("abnormal"),
        func.count().filter(online_between(new_from, new_to, backfill)).label("new"),
    ).group_by(Source.province_name)
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def online_by_day(session: AsyncSession, backfill: str) -> dict[str, int]:
    """每天上线多少（不含期初）：柱图各期和上一期的数量都从它加总。"""

    stmt = (
        select(Source.online_date, func.count())
        .where(online_between("", "9999-12-31", backfill))
        .group_by(Source.online_date)
    )
    return {day: int(number) for day, number in await session.execute(stmt)}


async def count_baseline(session: AsyncSession, backfill: str) -> int:
    """期初存量：上线时间是统一补填日的（不知道真实配置日），加上已爬但没填上线时间的。"""

    cond = or_(
        Source.online_date == backfill,
        and_(Source.crawler_status == CRAWLER_STATUS_ONLINE, Source.online_date == ""),
    )
    return int(await session.scalar(select(func.count()).where(cond)) or 0)


async def sites_online_between(session: AsyncSession, date_from: str, date_to: str, backfill: str) -> Sequence[Source]:
    stmt = select(Source).where(online_between(date_from, date_to, backfill)).order_by(*_DETAIL_ORDER)
    return (await session.scalars(stmt)).all()


async def abnormal_sites(session: AsyncSession) -> Sequence[Source]:
    stmt = select(Source).where(Source.crawler_status == CRAWLER_STATUS_ABNORMAL).order_by(*_DETAIL_ORDER)
    return (await session.scalars(stmt)).all()
