from __future__ import annotations

import uuid
from collections.abc import Callable

from platform_common.filters import Filters, ilike_any
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.policy.domain.fields import (
    AI_NOTE_INTERPRET_FAILED,
    AI_NOTE_OPPORTUNITY_FAILED,
    AI_NOTE_TYPE_EMPTY,
    AI_NOTE_TYPE_FAILED,
    AI_NOTE_TYPE_UNKNOWN,
)
from app.policy.domain.models import BaseTag


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    return await session.get(BaseTag, item_id)


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    """更新路径专用：锁住目标行，见 sources.get_for_update 的说明。"""

    return await session.get(BaseTag, item_id, with_for_update=True)


async def get_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    result = await session.execute(select(BaseTag).where(BaseTag.content_hash == digest))
    return result.scalar_one_or_none()


async def list_hashes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(BaseTag.content_hash))
    return set(result.scalars())


# 列表与导出共用同一份筛选定义，避免两边条件逐渐走偏。
FILTER_COLUMNS: dict[str, InstrumentedAttribute[str]] = {
    "policy_name": BaseTag.policy_name,
    "province_name": BaseTag.province_name,
    "policy_types": BaseTag.policy_types,
    "is_penetrate": BaseTag.is_penetrate,
    "need_interpret": BaseTag.need_interpret,
}


def _remark_starts(*prefixes: str) -> ColumnElement[bool]:
    # 备注各段用「；」连接，失败说明可能在开头也可能在中间。
    return or_(*(or_(BaseTag.remark.like(f"{p}%"), BaseTag.remark.like(f"%；{p}%")) for p in prefixes))


# 「打标状态」精确筛选：AI 打标失败待重打的、排着队的待办。它不是一列，不在 FILTER_COLUMNS 里。
AI_STATUS: dict[str, Callable[[], ColumnElement[bool]]] = {
    "类型判断失败": lambda: _remark_starts(AI_NOTE_TYPE_FAILED, AI_NOTE_TYPE_UNKNOWN, AI_NOTE_TYPE_EMPTY),
    "解读失败": lambda: _remark_starts(AI_NOTE_INTERPRET_FAILED),
    "市场机会失败": lambda: _remark_starts(AI_NOTE_OPPORTUNITY_FAILED),
    "等待重新判断类型": lambda: BaseTag.type_retag_at.is_not(None),
    "待解读": lambda: and_(
        BaseTag.need_interpret == "是", BaseTag.source_content_id.is_not(None), BaseTag.interpreted_at.is_(None)
    ),
    "待补市场机会": lambda: and_(BaseTag.interpreted_at.is_not(None), BaseTag.opportunity_at.is_(None)),
}
EXACT_FILTERS = ("ai_status",)


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        if key == "ai_status":
            statuses = [] if isinstance(value, int) else list(value or [])
            if statuses:
                conds.append(or_(*(AI_STATUS[item]() for item in statuses)))  # 不认识的状态 KeyError，API 转 422
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
) -> tuple[list[BaseTag], int]:
    conds = _conditions(filters)
    total = int(await session.scalar(select(func.count()).select_from(BaseTag).where(*conds)) or 0)
    result = await session.execute(
        select(BaseTag)
        .where(*conds)
        .order_by(BaseTag.province_code, BaseTag.policy_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(BaseTag).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[BaseTag]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(
        select(BaseTag).where(*_conditions(filters)).order_by(BaseTag.province_code, BaseTag.policy_name)
    )
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[BaseTag]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})
