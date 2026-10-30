from __future__ import annotations

import operator
import uuid
from collections.abc import Callable
from typing import Any, cast

from platform_common.filters import Filters, ilike_any
from sqlalchemy import ColumnElement, CursorResult, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.policy.domain.models import Source


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Source | None:
    return await session.get(Source, item_id)


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> Source | None:
    """更新路径专用：锁住目标行。

    version 比对是「先读后写」，发出的 UPDATE 不带版本条件。不加行锁时两个并发
    请求会读到同一个 version、双双通过校验，后提交的静默覆盖前一个，两边都收到 200。
    """

    return await session.get(Source, item_id, with_for_update=True)


async def get_many_for_update(session: AsyncSession, item_ids: list[uuid.UUID]) -> list[Source]:
    """批量改状态：一次锁住勾选的行，和单条编辑互斥。按主键排序加锁，避免两个批量请求交叉死锁。"""

    result = await session.execute(
        select(Source).where(Source.id.in_(set(item_ids))).order_by(Source.id).with_for_update()
    )
    return list(result.scalars())


async def get_by_internal_id(session: AsyncSession, internal_id: str) -> Source | None:
    result = await session.execute(select(Source).where(Source.internal_id == internal_id))
    return result.scalar_one_or_none()


async def get_by_site_code(session: AsyncSession, site_code: str) -> Source | None:
    result = await session.execute(select(Source).where(Source.site_code == site_code))
    return result.scalar_one_or_none()


async def list_internal_ids(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Source.internal_id))
    return set(result.scalars())


async def list_site_codes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Source.site_code))
    return set(result.scalars())


async def list_site_codes_for_district(session: AsyncSession, district_code: str) -> list[str]:
    prefix = district_code or ""
    if not prefix:
        # 空前缀是 LIKE '%'：会把整张信源表锁住。调用方先校验编码。
        raise ValueError("网站编码前缀为空")
    result = await session.execute(
        select(Source.site_code)
        .where(or_(Source.district_code == prefix, Source.site_code.startswith(prefix)))
        .with_for_update()
    )
    return list(result.scalars())


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "site_name": Source.site_name,
    "province_name": Source.province_name,
    "city_name": Source.city_name,
    "tag": Source.tag,
    "site_code": Source.site_code,
    "crawl_priority": Source.crawl_priority,
    "site_type": Source.site_type,
    "crawler_status": Source.crawler_status,
}

# 上线时间区间（含两端）。上线时间存 YYYY-MM-DD 文本，按字符串比较即按日期比较；没填上线时间的不落在任何区间里。
DATE_RANGE_FILTERS: dict[str, Callable[[Any, str], ColumnElement[bool]]] = {
    "online_date_from": operator.ge,
    "online_date_to": operator.le,
}


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        if key in DATE_RANGE_FILTERS:
            if isinstance(value, str) and value:
                conds.append(and_(Source.online_date != "", DATE_RANGE_FILTERS[key](Source.online_date, value)))
            continue
        column = FILTER_COLUMNS[key]  # 未知字段直接报错，避免筛选被静默忽略
        cond = ilike_any(column, value)
        if cond is not None:
            conds.append(cond)
    return conds


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[Source], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(Source).where(*conds)) or 0)
    result = await session.execute(
        select(Source)
        .where(*conds)
        .order_by(Source.site_code, Source.site_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(Source).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[Source]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(Source).where(*_conditions(filters)).order_by(Source.site_code, Source.site_name)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[Source]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


async def delete_all(session: AsyncSession) -> int:
    # execute() 的静态类型是 Result，DELETE 实际拿到的是带 rowcount 的 CursorResult。
    result = cast(CursorResult[Any], await session.execute(delete(Source)))
    return int(result.rowcount or 0)
