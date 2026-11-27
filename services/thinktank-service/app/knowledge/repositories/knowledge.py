"""资料库仓储：列表/导出共用筛选定义、权限范围过滤、动态码表选项、收藏与单文件操作日志。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from platform_common.filters import Filters, contains_ilike, filter_values, in_any
from platform_common.options import SEARCH_LIMIT, OptionColumns, preview_options, search_options
from sqlalchemy import ColumnElement, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.common.codebook_client import DEFAULT_THINKTANK_DICTS
from app.common.upload_utils import (
    expand_pipe_options,
    merge_unique,
    parse_favorite_only_filter,
    parse_tag_status_filter,
    pipe_match,
)
from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile
from app.knowledge.domain.scopes import (
    OPERATOR_TYPES,
    KnowledgeAccess,
    normalize_file_type_input,
)
from app.knowledge.repositories.interactions import (
    add_op_log,
    favorite_ids_for_user,
    is_favorited,
    list_op_logs,
    set_favorite,
)

__all__ = [
    "FILTER_COLUMNS",
    "OPTION_COLUMNS",
    "add_op_log",
    "count_filtered",
    "count_undefined",
    "favorite_ids_for_user",
    "get_by_file_name",
    "get_by_id",
    "get_for_update",
    "is_favorited",
    "list_filtered",
    "list_items",
    "list_op_logs",
    "list_options",
    "list_undefined",
    "search_option_values",
    "set_favorite",
]

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
    "file_type": KnowledgeFile.file_type,
    "depart_affiliation": KnowledgeFile.depart_affiliation,
    "industry_type": KnowledgeFile.industry_type,
    "product_type": KnowledgeFile.product_type,
    "product_sub_type": KnowledgeFile.product_sub_type,
    "app_scenario": KnowledgeFile.app_scenario,
    "market_category": KnowledgeFile.market_category,
    "prov_name": KnowledgeFile.prov_name,
    "data_time": KnowledgeFile.data_time,
}

_CODEBOOK_OPTION_MAP: dict[str, str] = {
    "file_type": "file_types",
    "depart_affiliation": "departments",
    "industry_type": "industries",
    "product_type": "product_types",
    "prov_name": "provinces",
    "market_category": "market_categories",
}

_PIPE_OPTION_FIELDS = frozenset({"industry_type", "product_type"})


def _pipe_match(column: Any, value: str) -> ColumnElement[bool]:
    return pipe_match(column, value)


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
        want_def = parse_tag_status_filter(vals)
        if want_def is not None:
            conds.append(KnowledgeFile.is_defined.is_(want_def))
    if (vals := filter_values(filters.get("favorite_only"))) and parse_favorite_only_filter(vals) and user_id:
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


def _dict_values(dicts: Mapping[str, Sequence[str]] | None, key: str) -> list[str]:
    if dicts is not None and key in dicts:
        return list(dicts[key])
    return list(DEFAULT_THINKTANK_DICTS[key])


def _db_items(raw: Mapping[str, dict[str, Any]], field: str) -> tuple[list[str], bool]:
    entry = raw.get(field) or {}
    items = list(entry.get("items") or [])
    if field in _PIPE_OPTION_FIELDS:
        items = expand_pipe_options(items)
    return items, bool(entry.get("truncated", False))


async def list_options(
    session: AsyncSession,
    *,
    access: KnowledgeAccess,
    dicts: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    raw = await preview_options(session, OPTION_COLUMNS, conditions=_scope_conditions(access))

    ft_db, _ = _db_items(raw, "file_type")
    ft_merged = merge_unique(_dict_values(dicts, "file_types"), ft_db, ["未定义"])
    allowed_ft = [label for label in ft_merged if ("" if label == "未定义" else label) in access.readable_file_types]
    raw["file_type"] = {"items": allowed_ft, "truncated": False}

    ind_db, _ = _db_items(raw, "industry_type")
    ind_merged = merge_unique(_dict_values(dicts, "industries"), ind_db)
    allowed_ind = [label for label in ind_merged if label in access.readable_industries]
    raw["industry_type"] = {"items": allowed_ind, "truncated": False}

    for field, dict_key in (
        ("depart_affiliation", "departments"),
        ("product_type", "product_types"),
        ("prov_name", "provinces"),
        ("market_category", "market_categories"),
    ):
        db_vals, truncated = _db_items(raw, field)
        raw[field] = {
            "items": merge_unique(_dict_values(dicts, dict_key), db_vals),
            "truncated": truncated,
        }

    raw["operator_type"] = {"items": list(OPERATOR_TYPES), "truncated": False}
    raw["tag_status"] = {"items": ["已定义", "未定义"], "truncated": False}
    raw["favorite_only"] = {"items": ["仅已收藏"], "truncated": False}
    return {"options": raw}


async def search_option_values(
    session: AsyncSession,
    *,
    field: str,
    keyword: str | None,
    dicts: Mapping[str, Sequence[str]] | None = None,
    access: KnowledgeAccess | None = None,
) -> list[str]:
    q = (keyword or "").strip()
    q_lower = q.lower()
    if field == "operator_type":
        return [item for item in OPERATOR_TYPES if not q_lower or q_lower in item.lower()][:SEARCH_LIMIT]
    if field not in OPTION_COLUMNS:
        raise KeyError(field)

    scope_conds = _scope_conditions(access) if access is not None else ()
    db_matches = await search_options(
        session,
        OPTION_COLUMNS,
        field=field,
        keyword=keyword,
        limit=SEARCH_LIMIT,
        conditions=scope_conds,
    )
    if field in _PIPE_OPTION_FIELDS:
        db_matches = [item for item in expand_pipe_options(db_matches) if not q_lower or q_lower in item.lower()]

    if dict_key := _CODEBOOK_OPTION_MAP.get(field):
        base = _dict_values(dicts, dict_key)
        if field == "file_type":
            base = [*base, "未定义"]
        merged = merge_unique(base, db_matches)
        if access is not None:
            if field == "file_type":
                merged = [v for v in merged if ("" if v == "未定义" else v) in access.readable_file_types]
            elif field == "industry_type":
                merged = [v for v in merged if v in access.readable_industries]
        return [v for v in merged if not q_lower or q_lower in v.lower()][:SEARCH_LIMIT]

    return db_matches[:SEARCH_LIMIT]
