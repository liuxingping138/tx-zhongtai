from __future__ import annotations

import uuid
from typing import Any

from platform_common.filters import LIKE_ESCAPE, contains_ilike, escape_like, filter_values
from platform_common.options import PREVIEW_LIMIT, SEARCH_LIMIT, OptionColumn, OptionColumns
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.filters import EventFilters
from app.domain.models import AuditEvent


def apply_filters[S: (Select[tuple[AuditEvent]], Select[tuple[int]])](stmt: S, filters: EventFilters) -> S:
    if filters.occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < filters.occurred_to)
    if filters.actor_id:
        stmt = stmt.where(AuditEvent.actor_id == filters.actor_id)
    names = filter_values(filters.actor_name)
    if names:
        stmt = stmt.where(
            or_(*(AuditEvent.actor_name_snapshot.like(f"%{escape_like(name)}%", escape=LIKE_ESCAPE) for name in names))
        )
    for column, value in (
        (AuditEvent.module_code, filters.module_code),
        (AuditEvent.action_code, filters.action_code),
        (AuditEvent.outcome, filters.outcome),
    ):
        values = filter_values(value)
        if values:
            stmt = stmt.where(column.in_(values))
    return stmt


async def count_events(session: AsyncSession, filters: EventFilters) -> int:
    stmt = apply_filters(select(func.count()).select_from(AuditEvent), filters)
    return int((await session.execute(stmt)).scalar_one())


async def list_events(session: AsyncSession, filters: EventFilters, *, offset: int, limit: int) -> list[AuditEvent]:
    stmt = apply_filters(select(AuditEvent), filters)
    stmt = stmt.order_by(AuditEvent.occurred_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# 筛选项字段。键名与列表接口的 query 参数一致，便于前端直接按字段名绑定。
# 三列都有以它打头的索引（actor_name、action_code 各一个，module_code 用 module_action 组合索引），
# 取候选值靠 _distinct_values 沿索引跳着走，不整表去重。
OPTION_COLUMNS: OptionColumns = {
    "actor_name": AuditEvent.actor_name_snapshot,
    "module_code": AuditEvent.module_code,
    "action_code": AuditEvent.action_code,
}


def distinct_values_stmt(column: OptionColumn, *, keyword: str | None, limit: int) -> Select[tuple[str]]:
    """某列不同的非空值，按值排序。

    整表 DISTINCT 要读完每一行（操作日志只增不改，越积越多）；这里用递归查询模拟「跳跃式索引扫描」：
    从最小的值开始，每一步用索引找「比上一个大的最小值」，步数等于不同值的个数（几十个人、二十来个模块），
    与表有多少行无关。`> ''` 同时去掉空值和空串。
    """

    step_table = aliased(AuditEvent)
    step_column = getattr(step_table, column.key)
    first = select(func.min(column).label("value")).where(column > "")
    walk = first.cte("walk", recursive=True)
    following = select(func.min(step_column)).where(step_column > walk.c.value).scalar_subquery()
    walk = walk.union_all(select(following).where(walk.c.value.is_not(None)))
    stmt = select(walk.c.value).where(walk.c.value.is_not(None))
    text = (keyword or "").strip()
    if text:
        stmt = stmt.where(contains_ilike(walk.c.value, text))
    return stmt.order_by(walk.c.value).limit(limit)


async def _distinct_values(
    session: AsyncSession, column: OptionColumn, *, keyword: str | None, limit: int
) -> list[str]:
    result = await session.execute(distinct_values_stmt(column, keyword=keyword, limit=limit))
    return [value for value in result.scalars() if value]


async def list_options(session: AsyncSession) -> dict[str, Any]:
    """每个字段给前 PREVIEW_LIMIT 个候选并标明是否截断，形状同 platform_common.options.preview_options。"""

    out: dict[str, dict[str, Any]] = {}
    for field, column in OPTION_COLUMNS.items():
        rows = await _distinct_values(session, column, keyword=None, limit=PREVIEW_LIMIT + 1)
        out[field] = {"items": rows[:PREVIEW_LIMIT], "truncated": len(rows) > PREVIEW_LIMIT}
    return {"options": out}


async def search_option_values(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """未知字段直接 KeyError（接口转 422），不静默返回空列表。"""

    return await _distinct_values(session, OPTION_COLUMNS[field], keyword=keyword, limit=SEARCH_LIMIT)


async def get_event(session: AsyncSession, event_pk: uuid.UUID) -> AuditEvent | None:
    result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_pk))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    result = await session.execute(select(AuditEvent).where(AuditEvent.event_id == event_pk))
    return result.scalar_one_or_none()
