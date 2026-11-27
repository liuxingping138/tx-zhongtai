"""智库专属 6 张码表仓储层。"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from platform_common.filters import Filters, contains_ilike, filter_values
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ThinktankDict
from app.domain.thinktank_dicts import THINKTANK_DICT_SPECS

ORDER_BY = (
    ThinktankDict.sort_order.asc(),
    ThinktankDict.created_at.asc(),
    ThinktankDict.name.asc(),
)


def _conditions(dict_type: str, filters: Filters) -> list[ColumnElement[bool]]:
    unknown = set(filters) - {"keyword"}
    if unknown:
        raise KeyError(f"未知筛选字段: {sorted(unknown)}")
    conds: list[ColumnElement[bool]] = [ThinktankDict.dict_type == dict_type]
    keywords = filter_values(filters.get("keyword"))
    if keywords:
        conds.append(or_(*(contains_ilike(ThinktankDict.name, word) for word in keywords)))
    return conds


async def get_for_update(session: AsyncSession, dict_type: str, item_id: uuid.UUID) -> ThinktankDict | None:
    """更新与删除路径专用：按 (dict_type, id) 锁住目标行，防止跨码表越权修改。"""

    stmt = (
        select(ThinktankDict).where(ThinktankDict.id == item_id, ThinktankDict.dict_type == dict_type).with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_name(session: AsyncSession, dict_type: str, name: str, *, lock: bool = False) -> ThinktankDict | None:
    stmt = select(ThinktankDict).where(ThinktankDict.dict_type == dict_type, ThinktankDict.name == name)
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def existing_names(session: AsyncSession, dict_type: str, names: Iterable[str]) -> set[str]:
    candidates = {item for item in names if item}
    if not candidates:
        return set()
    stmt = select(ThinktankDict.name).where(ThinktankDict.dict_type == dict_type, ThinktankDict.name.in_(candidates))
    return set((await session.execute(stmt)).scalars())


async def list_items(
    session: AsyncSession,
    dict_type: str,
    *,
    filters: Filters,
    page: int,
    page_size: int,
) -> tuple[list[ThinktankDict], int]:
    conds = _conditions(dict_type, filters)
    total = int(await session.scalar(select(func.count()).select_from(ThinktankDict).where(*conds)) or 0)
    stmt = select(ThinktankDict).where(*conds).order_by(*ORDER_BY).offset((page - 1) * page_size).limit(page_size)
    return list((await session.execute(stmt)).scalars()), total


async def count_filtered(session: AsyncSession, dict_type: str, filters: Filters) -> int:
    conds = _conditions(dict_type, filters)
    return int(await session.scalar(select(func.count()).select_from(ThinktankDict).where(*conds)) or 0)


async def list_filtered(session: AsyncSession, dict_type: str, filters: Filters) -> list[ThinktankDict]:
    conds = _conditions(dict_type, filters)
    stmt = select(ThinktankDict).where(*conds).order_by(*ORDER_BY)
    return list((await session.execute(stmt)).scalars())


async def list_all_grouped(session: AsyncSession) -> dict[str, list[str]]:
    """一次查询返回 6 张智库码表的全部名称，严格按 sort_order ASC, created_at ASC, name ASC 排序。"""

    grouped: dict[str, list[str]] = {spec.dict_type: [] for spec in THINKTANK_DICT_SPECS}
    stmt = select(ThinktankDict.dict_type, ThinktankDict.name).order_by(*ORDER_BY)
    for dict_type, name in (await session.execute(stmt)).all():
        if dict_type in grouped and name:
            grouped[dict_type].append(name)
    return grouped


async def delete_item(session: AsyncSession, row: ThinktankDict) -> None:
    await session.delete(row)


async def insert_seed_rows(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """幂等写入种子行（ON CONFLICT DO NOTHING），返回实际新增条数。"""

    if not rows:
        return 0
    stmt = (
        pg_insert(ThinktankDict).values(rows).on_conflict_do_nothing(constraint="uq_codebook_thinktank_dicts_type_name")
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)
