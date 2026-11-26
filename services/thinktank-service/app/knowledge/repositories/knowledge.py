"""知识库仓储：列表/导出共用筛选定义、权限范围过滤、收藏与单文件操作日志。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.clock import utcnow
from platform_common.filters import LIKE_ESCAPE, Filters, contains_ilike, escape_like, filter_values, in_any
from platform_common.options import SEARCH_LIMIT, OptionColumns, preview_options, search_options
from sqlalchemy import ColumnElement, delete, exists, false, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile, KnowledgeOpLog
from app.knowledge.domain.scopes import (
    FILE_TYPES,
    INDUSTRY_TYPES,
    MARKET_CATEGORIES,
    OPERATOR_TYPES,
    PRODUCT_TYPES,
    PROVINCES,
    KnowledgeAccess,
    normalize_file_type_input,
)

# 列表与导出共用同一份筛选键集合，未知键直接抛 KeyError（接口层转 422）。
FILTER_COLUMNS: dict[str, str] = {
    "file_name": "keyword",
    "file_type": "file_type",
    "operator_type": "exact",
    "product_type": "pipe",
    "product_sub_type": "keyword",
    "industry_type": "pipe_industry",
    "prov_name": "exact",
    "app_scenario": "keyword",
    "depart_affiliation": "keyword",
    "market_category": "exact",
    "data_time": "keyword",
    "tag_status": "tag_status",
    "favorite_only": "favorite_only",
}

OPTION_COLUMNS: OptionColumns = {
    "depart_affiliation": KnowledgeFile.depart_affiliation,
    "app_scenario": KnowledgeFile.app_scenario,
    "prov_name": KnowledgeFile.prov_name,
    "data_time": KnowledgeFile.data_time,
}


def _pipe_match(column: Any, value: str) -> ColumnElement[bool]:
    escaped = escape_like(value)
    return or_(
        column == value,
        column.like(f"{escaped}|%", escape=LIKE_ESCAPE),
        column.like(f"%|{escaped}", escape=LIKE_ESCAPE),
        column.like(f"%|{escaped}|%", escape=LIKE_ESCAPE),
    )


def _industry_scope_condition(allowed_industries: frozenset[str]) -> ColumnElement[bool]:
    if not allowed_industries:
        return false()
    clauses: list[ColumnElement[bool]] = [
        _pipe_match(KnowledgeFile.industry_type, ind) for ind in sorted(allowed_industries)
    ]
    if "无" in allowed_industries:
        clauses.append(KnowledgeFile.industry_type == "")
    return or_(*clauses)


def _scope_conditions(access: KnowledgeAccess, *, export_mode: bool = False) -> list[ColumnElement[bool]]:
    allowed_ft = access.exportable_file_types if export_mode else access.readable_file_types
    allowed_ind = access.exportable_industries if export_mode else access.readable_industries
    if not allowed_ft or not allowed_ind:
        return [false()]
    return [
        KnowledgeFile.file_type.in_(sorted(allowed_ft)),
        _industry_scope_condition(allowed_ind),
    ]


def _text_and_tag_conditions(filters: Filters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if vals := filter_values(filters.get("file_name")):
        conds.append(or_(*(contains_ilike(KnowledgeFile.file_name, v) for v in vals)))
    if vals := filter_values(filters.get("file_type")):
        conds.append(KnowledgeFile.file_type.in_([normalize_file_type_input(v) for v in vals]))
    for field, col in (
        ("operator_type", KnowledgeFile.operator_type),
        ("prov_name", KnowledgeFile.prov_name),
        ("market_category", KnowledgeFile.market_category),
    ):
        if (cond := in_any(col, filters.get(field))) is not None:
            conds.append(cond)
    for field, col in (
        ("product_sub_type", KnowledgeFile.product_sub_type),
        ("app_scenario", KnowledgeFile.app_scenario),
        ("depart_affiliation", KnowledgeFile.depart_affiliation),
        ("data_time", KnowledgeFile.data_time),
    ):
        if vals := filter_values(filters.get(field)):
            conds.append(or_(*(contains_ilike(col, v) for v in vals)))
    return conds


def _scope_and_status_conditions(filters: Filters, *, user_id: str | None) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if vals := filter_values(filters.get("product_type")):
        conds.append(or_(*(_pipe_match(KnowledgeFile.product_type, v) for v in vals)))
    if vals := filter_values(filters.get("industry_type")):
        clauses = [_pipe_match(KnowledgeFile.industry_type, v) for v in vals]
        if "无" in vals:
            clauses.append(KnowledgeFile.industry_type == "")
        conds.append(or_(*clauses))
    if vals := filter_values(filters.get("tag_status")):
        want_def, want_undef = "已定义" in vals, "未定义" in vals
        if want_def != want_undef:
            conds.append(KnowledgeFile.is_defined.is_(want_def))
    if (vals := filter_values(filters.get("favorite_only"))) and (("已收藏" in vals or "仅已收藏" in vals) and user_id):
        conds.append(
            exists().where(KnowledgeFavorite.user_id == user_id, KnowledgeFavorite.file_id == KnowledgeFile.id)
        )
    return conds


def _conditions(
    filters: Filters,
    *,
    user_id: str | None = None,
) -> list[ColumnElement[bool]]:
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise KeyError(f"未知筛选字段: {sorted(unknown)}")
    return [*_text_and_tag_conditions(filters), *_scope_and_status_conditions(filters, user_id=user_id)]


async def get_by_id(session: AsyncSession, file_id: uuid.UUID) -> KnowledgeFile | None:
    return await session.get(KnowledgeFile, file_id)


async def get_for_update(session: AsyncSession, file_id: uuid.UUID) -> KnowledgeFile | None:
    return await session.get(KnowledgeFile, file_id, with_for_update=True)


async def get_by_file_name(session: AsyncSession, file_name: str) -> KnowledgeFile | None:
    stmt = select(KnowledgeFile).where(KnowledgeFile.file_name == file_name).order_by(KnowledgeFile.uploaded_at.desc())
    result = await session.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def list_items(
    session: AsyncSession,
    *,
    filters: Filters,
    access: KnowledgeAccess,
    user_id: str,
    page: int,
    page_size: int,
) -> tuple[list[KnowledgeFile], int]:
    conds = [*_scope_conditions(access), *_conditions(filters, user_id=user_id)]
    total = int(await session.scalar(select(func.count()).select_from(KnowledgeFile).where(*conds)) or 0)
    stmt = (
        select(KnowledgeFile)
        .options(defer(KnowledgeFile.content_text))
        .where(*conds)
        .order_by(KnowledgeFile.uploaded_at.desc(), KnowledgeFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    return list(result.scalars()), total


async def count_filtered(
    session: AsyncSession,
    filters: Filters,
    *,
    access: KnowledgeAccess,
    user_id: str,
) -> int:
    conds = [*_scope_conditions(access, export_mode=True), *_conditions(filters, user_id=user_id)]
    return int(await session.scalar(select(func.count()).select_from(KnowledgeFile).where(*conds)) or 0)


async def list_filtered(
    session: AsyncSession,
    filters: Filters,
    *,
    access: KnowledgeAccess,
    user_id: str,
) -> list[KnowledgeFile]:
    conds = [*_scope_conditions(access, export_mode=True), *_conditions(filters, user_id=user_id)]
    stmt = (
        select(KnowledgeFile)
        .options(defer(KnowledgeFile.content_text), defer(KnowledgeFile.remark))
        .where(*conds)
        .order_by(KnowledgeFile.uploaded_at.desc(), KnowledgeFile.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def count_undefined(
    session: AsyncSession,
    *,
    access: KnowledgeAccess,
) -> int:
    conds = [
        *_scope_conditions(access, export_mode=True),
        KnowledgeFile.is_defined.is_(False),
    ]
    return int(await session.scalar(select(func.count()).select_from(KnowledgeFile).where(*conds)) or 0)


async def list_undefined(
    session: AsyncSession,
    *,
    access: KnowledgeAccess,
) -> list[KnowledgeFile]:
    conds = [
        *_scope_conditions(access, export_mode=True),
        KnowledgeFile.is_defined.is_(False),
    ]
    stmt = (
        select(KnowledgeFile)
        .options(defer(KnowledgeFile.content_text))
        .where(*conds)
        .order_by(KnowledgeFile.uploaded_at.desc(), KnowledgeFile.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def favorite_ids_for_user(
    session: AsyncSession,
    *,
    user_id: str,
    file_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not file_ids:
        return set()
    stmt = select(KnowledgeFavorite.file_id).where(
        KnowledgeFavorite.user_id == user_id,
        KnowledgeFavorite.file_id.in_(file_ids),
    )
    return set((await session.execute(stmt)).scalars())


async def is_favorited(session: AsyncSession, *, user_id: str, file_id: uuid.UUID) -> bool:
    stmt = select(KnowledgeFavorite.file_id).where(
        KnowledgeFavorite.user_id == user_id,
        KnowledgeFavorite.file_id == file_id,
    )
    return (await session.scalar(stmt)) is not None


async def set_favorite(session: AsyncSession, *, user_id: str, file_id: uuid.UUID, favorite: bool) -> bool:
    if favorite:
        stmt = (
            pg_insert(KnowledgeFavorite)
            .values(user_id=user_id, file_id=file_id, created_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "file_id"])
            .returning(KnowledgeFavorite.file_id)
        )
        return (await session.scalar(stmt)) is not None
    del_stmt = (
        delete(KnowledgeFavorite)
        .where(
            KnowledgeFavorite.user_id == user_id,
            KnowledgeFavorite.file_id == file_id,
        )
        .returning(KnowledgeFavorite.file_id)
    )
    return (await session.scalar(del_stmt)) is not None


async def add_op_log(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    actor_id: str,
    actor_name: str,
    op_type: str,
    detail: str = "",
) -> KnowledgeOpLog:
    row = KnowledgeOpLog(
        file_id=file_id,
        actor_id=actor_id,
        actor_name=actor_name,
        op_type=op_type,
        detail=detail,
        created_at=utcnow(),
    )
    session.add(row)
    return row


async def list_op_logs(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[KnowledgeOpLog], int]:
    total = int(
        await session.scalar(select(func.count()).select_from(KnowledgeOpLog).where(KnowledgeOpLog.file_id == file_id))
        or 0
    )
    stmt = (
        select(KnowledgeOpLog)
        .where(KnowledgeOpLog.file_id == file_id)
        .order_by(KnowledgeOpLog.created_at.desc(), KnowledgeOpLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.execute(stmt)).scalars()), total


async def list_options(
    session: AsyncSession,
    *,
    access: KnowledgeAccess,
    provinces: list[str] | None = None,
) -> dict[str, Any]:
    raw = await preview_options(session, OPTION_COLUMNS, conditions=_scope_conditions(access))
    allowed_ft = [
        label for label in (*FILE_TYPES, "未定义") if ("" if label == "未定义" else label) in access.readable_file_types
    ]
    allowed_ind = [label for label in INDUSTRY_TYPES if label in access.readable_industries]
    raw["file_type"] = {"items": allowed_ft, "truncated": False}
    raw["industry_type"] = {"items": allowed_ind, "truncated": False}
    raw["operator_type"] = {"items": list(OPERATOR_TYPES), "truncated": False}
    raw["product_type"] = {"items": list(PRODUCT_TYPES), "truncated": False}
    raw["market_category"] = {"items": list(MARKET_CATEGORIES), "truncated": False}
    raw["prov_name"] = {"items": list(provinces) if provinces is not None else list(PROVINCES), "truncated": False}
    raw["tag_status"] = {"items": ["已定义", "未定义"], "truncated": False}
    raw["favorite_only"] = {"items": ["仅已收藏"], "truncated": False}
    return {"options": raw}


async def search_option_values(
    session: AsyncSession,
    *,
    field: str,
    keyword: str | None,
    provinces: list[str] | None = None,
    access: KnowledgeAccess | None = None,
) -> list[str]:
    if field == "prov_name":
        q = (keyword or "").strip()
        source = provinces if provinces is not None else list(PROVINCES)
        return [p for p in source if not q or q in p][:SEARCH_LIMIT]
    scope_conds = _scope_conditions(access) if access is not None else ()
    return await search_options(
        session,
        OPTION_COLUMNS,
        field=field,
        keyword=keyword,
        limit=SEARCH_LIMIT,
        conditions=scope_conds,
    )
