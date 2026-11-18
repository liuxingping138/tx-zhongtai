"""筛选项（下拉候选值）的预览与服务端搜索。

历史实现是一次性把每个字段的全部去重值发给前端（上限 8000），由前端做
本地过滤。这有两个问题：

1. 正确性：基数超过上限的字段会被静默截断——信源的网站名称有 1 万多个
   不同值，排序靠后的那些在下拉里永远搜不到。
2. 体积：单次响应接近 1MB，每进一次列表页都要传一遍。

现在改为「少量预览 + 服务端搜索」：基数小的字段照旧整份返回，基数大的
字段只返回前 ``PREVIEW_LIMIT`` 个并标记 ``truncated``，由前端在用户输入
关键词时调搜索接口。截断字段不再有搜不到的值。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from platform_common.filters import contains_ilike

# 不输入关键词时直接给出的候选数量。超过这个基数的字段转为服务端搜索。
PREVIEW_LIMIT = 200
# 每次搜索返回的候选数量。
SEARCH_LIMIT = 50

# 可空列也能做筛选项，空值在查询里过滤掉。
OptionColumn = InstrumentedAttribute[str] | InstrumentedAttribute[str | None]
OptionColumns = Mapping[str, OptionColumn]


async def _distinct(
    session: AsyncSession,
    column: OptionColumn,
    limit: int,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> list[str]:
    stmt = select(column).where(column.is_not(None)).where(column != "")
    if conditions:
        stmt = stmt.where(*conditions)
    result = await session.execute(stmt.distinct().order_by(column).limit(limit))
    return [value for value in result.scalars() if value]


async def preview_options(
    session: AsyncSession,
    columns: OptionColumns,
    *,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> dict[str, dict[str, Any]]:
    """每个字段返回前 PREVIEW_LIMIT 个候选，并标明是否被截断。

    多取一条用于判断截断，不需要再跑一次 count。
    """

    out: dict[str, dict[str, Any]] = {}
    for field, column in columns.items():
        rows = (
            await _distinct(session, column, PREVIEW_LIMIT + 1, conditions=conditions)
            if conditions
            else await _distinct(session, column, PREVIEW_LIMIT + 1)
        )
        out[field] = {
            "items": rows[:PREVIEW_LIMIT],
            "truncated": len(rows) > PREVIEW_LIMIT,
        }
    return out


async def search_options(
    session: AsyncSession,
    columns: OptionColumns,
    *,
    field: str,
    keyword: str | None,
    limit: int = SEARCH_LIMIT,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> list[str]:
    """按关键词搜索某个字段的候选值。

    未知字段直接 KeyError，不静默返回空列表——否则前端拼错字段名时
    下拉会一直是空的，很难排查。
    """

    column = columns[field]
    text = (keyword or "").strip()
    stmt = select(column).where(column.is_not(None)).where(column != "")
    if conditions:
        stmt = stmt.where(*conditions)
    if text:
        stmt = stmt.where(contains_ilike(column, text))
    result = await session.execute(stmt.distinct().order_by(column).limit(limit))
    return [value for value in result.scalars() if value]
