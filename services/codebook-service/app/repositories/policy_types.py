from __future__ import annotations

import uuid

from platform_common.filters import Filters
from sqlalchemy import ColumnElement, Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PolicyType


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> PolicyType | None:
    return await session.get(PolicyType, item_id)


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> PolicyType | None:
    """更新路径专用：锁住目标行。

    version 比对是「先读后写」，发出的 UPDATE 不带版本条件。不加行锁时两个并发
    请求会读到同一个 version、双双通过校验，后提交的静默覆盖前一个，两边都收到 200。
    """

    return await session.get(PolicyType, item_id, with_for_update=True)


async def get_by_name(session: AsyncSession, type_name: str) -> PolicyType | None:
    result = await session.execute(select(PolicyType).where(PolicyType.type_name == type_name))
    return result.scalar_one_or_none()


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
# 政策类型只有一个关键词，跨三列做 or 匹配。
KEYWORD_COLUMNS = (PolicyType.type_name, PolicyType.definition, PolicyType.seq_no)
_ORDER_BY = (cast(func.nullif(PolicyType.seq_no, ""), Integer), PolicyType.type_name)


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    keyword = filters.get("keyword")
    unknown = set(filters) - {"keyword"}
    if unknown:  # 未知字段直接报错，避免筛选被静默忽略
        raise KeyError(f"未知筛选字段: {sorted(unknown)}")
    if not keyword:
        return []
    like = f"%{keyword}%"
    return [or_(*(column.ilike(like) for column in KEYWORD_COLUMNS))]


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[PolicyType], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(PolicyType).where(*conds)) or 0)
    result = await session.execute(
        select(PolicyType)
        .where(*conds)
        .order_by(*_ORDER_BY)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(PolicyType).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[PolicyType]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(PolicyType).where(*_conditions(filters)).order_by(*_ORDER_BY)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[PolicyType]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})


