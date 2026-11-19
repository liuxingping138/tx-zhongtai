from __future__ import annotations

import uuid
from collections.abc import Callable, Collection

from platform_common.filters import Filters, ilike_any
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.policy.domain.fields import AI_NOTE_INTERPRET_FAILED, AI_NOTE_OPPORTUNITY_FAILED, TYPE_NOTES
from app.policy.domain.models import BaseTag, awaiting_interpretation, awaiting_opportunity

# 列表、导出共用的排序。最后按 ID 兜底：同名的记录每次查询先后一致，翻页不重复不漏，
# 详情页按位置取上一条、下一条也不会跳乱。
_ORDER = (BaseTag.province_code, BaseTag.policy_name, BaseTag.id)


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    return await session.get(BaseTag, item_id)


async def get_for_update(session: AsyncSession, item_id: uuid.UUID) -> BaseTag | None:
    """更新路径专用：锁住目标行，见 sources.get_for_update 的说明。"""

    return await session.get(BaseTag, item_id, with_for_update=True)


async def get_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    result = await session.execute(select(BaseTag).where(BaseTag.content_hash == digest))
    return result.scalar_one_or_none()


async def existing_hashes(session: AsyncSession, digests: Collection[str]) -> set[str]:
    """文件里这些内容哈希哪些库里已有。按文件分片查，不把几百万行的哈希整表拉进内存。"""

    found: set[str] = set()
    wanted = list(set(digests))
    for start in range(0, len(wanted), IN_CHUNK):
        chunk = wanted[start : start + IN_CHUNK]
        result = await session.execute(select(BaseTag.content_hash).where(BaseTag.content_hash.in_(chunk)))
        found.update(result.scalars())
    return found


# IN (...) 一次最多带这么多个值。
IN_CHUNK = 1000

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


# 「打标状态」精确筛选：AI 打标失败待重打的、排着队的待办。它不是库里的一列，不在 FILTER_COLUMNS 里；
# 列表上的「打标状态」列由 domain.fields.ai_status 按同样的条件算，改这里要一起改。
# 已经排进「重新判断类型」的不再算类型判断失败：申请重判时会去掉失败说明，这里再兜住申请前留下的旧备注，
# 免得列表还显示失败、用户以为没生效又点一次。
AI_STATUS: dict[str, Callable[[], ColumnElement[bool]]] = {
    "类型判断失败": lambda: and_(
        BaseTag.type_retag_at.is_(None),
        _remark_starts(*TYPE_NOTES),
    ),
    "解读失败": lambda: _remark_starts(AI_NOTE_INTERPRET_FAILED),
    "市场机会失败": lambda: _remark_starts(AI_NOTE_OPPORTUNITY_FAILED),
    "等待重新判断类型": lambda: BaseTag.type_retag_at.is_not(None),
    "待解读": awaiting_interpretation,
    "待补市场机会": awaiting_opportunity,
}
EXACT_FILTERS = ("ai_status", "is_policy", "is_info_policy")


def _str_list(value: object) -> list[str]:
    if isinstance(value, (int, str)) or not isinstance(value, Collection):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    for key, value in filters.items():
        if key == "ai_status":
            statuses = _str_list(value)
            if statuses:
                conds.append(or_(*(AI_STATUS[item]() for item in statuses)))  # 不认识的状态 KeyError，API 转 422
            continue
        if key == "is_policy":
            if values := _str_list(value):
                conds.append(BaseTag.ai_outputs["是否政策"].astext.in_(values))
            continue
        if key == "is_info_policy":
            if values := _str_list(value):
                expr = func.coalesce(
                    func.nullif(BaseTag.ai_outputs["是否信息化政策"].astext, ""), BaseTag.need_interpret
                )
                conds.append(expr.in_(values))
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
    result = await session.execute(
        select(BaseTag).where(*conds).order_by(*_ORDER).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars())
    if len(items) < page_size and (page == 1 or items):
        return items, (page - 1) * page_size + len(items)
    total = int(await session.scalar(select(func.count()).select_from(BaseTag).where(*conds)) or 0)
    return items, total


async def count_filtered(session: AsyncSession, filters: Filters) -> int:
    """导出前按同样的筛选条件数行数，避免把超限的结果集读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(BaseTag).where(*_conditions(filters))) or 0)


async def list_filtered(session: AsyncSession, filters: Filters) -> list[BaseTag]:
    """导出用：与列表一致的筛选和排序，不分页。"""

    result = await session.execute(select(BaseTag).where(*_conditions(filters)).order_by(*_ORDER))
    return list(result.scalars())


async def list_all(session: AsyncSession) -> list[BaseTag]:
    """全表读取（不筛选）。导出请用 list_filtered，两者排序一致。"""

    return await list_filtered(session, {})
