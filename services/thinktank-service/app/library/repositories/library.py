"""报告库与方案库通用仓储：筛选、分页、导出、未定义、收藏、日志与动态码表选项。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.filters import Filters, contains_ilike, filter_values, in_any
from platform_common.options import SEARCH_LIMIT, preview_options, search_options
from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
from app.library.domain.specs import LibrarySpec


def _field_condition(
    spec: LibrarySpec,
    field: str,
    kind: str,
    raw: Any,
    user_id: str | None,
) -> ColumnElement[bool] | None:
    vals = filter_values(raw)
    if not vals:
        return None
    cond: ColumnElement[bool] | None = None
    if kind == "keyword":
        cond = or_(*(contains_ilike(spec.column(field), v) for v in vals))
    elif kind == "exact":
        cond = in_any(spec.column(field), raw)
    elif kind == "pipe":
        cond = or_(*(pipe_match(spec.column(field), v) for v in vals))
    elif kind == "tag_status":
        want_def = parse_tag_status_filter(vals)
        cond = spec.file_model.is_defined.is_(want_def) if want_def is not None else None
    elif kind == "favorite_only" and parse_favorite_only_filter(vals) and user_id:
        fav = spec.favorite_model
        cond = exists().where(fav.user_id == user_id, fav.file_id == spec.file_model.id)
    return cond


def build_conditions(
    spec: LibrarySpec,
    filters: Filters,
    *,
    user_id: str | None = None,
) -> list[ColumnElement[bool]]:
    unknown = set(filters) - set(spec.filter_kinds)
    if unknown:
        raise KeyError(f"未知筛选字段: {sorted(unknown)}")
    conds: list[ColumnElement[bool]] = []
    for field, kind in spec.filter_kinds.items():
        if (cond := _field_condition(spec, field, kind, filters.get(field), user_id)) is not None:
            conds.append(cond)
    return conds


async def get_by_id(session: AsyncSession, spec: LibrarySpec, file_id: uuid.UUID) -> Any | None:
    return await session.get(spec.file_model, file_id)


async def get_for_update(session: AsyncSession, spec: LibrarySpec, file_id: uuid.UUID) -> Any | None:
    return await session.get(spec.file_model, file_id, with_for_update=True)


async def get_by_title(session: AsyncSession, spec: LibrarySpec, title: str) -> Any | None:
    model = spec.file_model
    col = spec.column(spec.title_field)
    stmt = select(model).where(col == title).order_by(model.uploaded_at.desc())
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def list_items(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    filters: Filters,
    user_id: str,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    model = spec.file_model
    conds = build_conditions(spec, filters, user_id=user_id)
    total = int(await session.scalar(select(func.count()).select_from(model).where(*conds)) or 0)
    stmt = (
        select(model)
        .options(defer(model.content_text))
        .where(*conds)
        .order_by(model.uploaded_at.desc(), model.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.execute(stmt)).scalars()), total


async def count_filtered(
    session: AsyncSession,
    spec: LibrarySpec,
    filters: Filters,
    *,
    user_id: str,
) -> int:
    model = spec.file_model
    conds = build_conditions(spec, filters, user_id=user_id)
    return int(await session.scalar(select(func.count()).select_from(model).where(*conds)) or 0)


async def list_filtered(
    session: AsyncSession,
    spec: LibrarySpec,
    filters: Filters,
    *,
    user_id: str,
) -> list[Any]:
    model = spec.file_model
    conds = build_conditions(spec, filters, user_id=user_id)
    stmt = (
        select(model)
        .options(defer(model.content_text), defer(model.remark))
        .where(*conds)
        .order_by(model.uploaded_at.desc(), model.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def count_undefined(session: AsyncSession, spec: LibrarySpec) -> int:
    model = spec.file_model
    return int(await session.scalar(select(func.count()).select_from(model).where(model.is_defined.is_(False))) or 0)


async def list_undefined(session: AsyncSession, spec: LibrarySpec) -> list[Any]:
    model = spec.file_model
    stmt = (
        select(model)
        .options(defer(model.content_text))
        .where(model.is_defined.is_(False))
        .order_by(model.uploaded_at.desc(), model.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def favorite_ids_for_user(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    user_id: str,
    file_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not file_ids:
        return set()
    fav = spec.favorite_model
    stmt = select(fav.file_id).where(fav.user_id == user_id, fav.file_id.in_(file_ids))
    return set((await session.execute(stmt)).scalars())


async def is_favorited(session: AsyncSession, spec: LibrarySpec, *, user_id: str, file_id: uuid.UUID) -> bool:
    fav = spec.favorite_model
    stmt = select(fav.file_id).where(fav.user_id == user_id, fav.file_id == file_id)
    return (await session.scalar(stmt)) is not None


async def set_favorite(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    user_id: str,
    file_id: uuid.UUID,
    favorite: bool,
) -> bool:
    fav = spec.favorite_model
    if favorite:
        stmt = (
            pg_insert(fav)
            .values(user_id=user_id, file_id=file_id, created_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "file_id"])
            .returning(fav.file_id)
        )
        return (await session.scalar(stmt)) is not None
    del_stmt = delete(fav).where(fav.user_id == user_id, fav.file_id == file_id).returning(fav.file_id)
    return (await session.scalar(del_stmt)) is not None


async def add_op_log(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    file_id: uuid.UUID,
    actor: Actor,
    op_type: str,
    detail: str = "",
) -> Any:
    row = spec.log_model(
        file_id=file_id,
        actor_id=actor.id,
        actor_name=actor.name,
        op_type=op_type,
        detail=detail,
        created_at=utcnow(),
    )
    session.add(row)
    return row


async def list_op_logs(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    file_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    log_model = spec.log_model
    total = int(
        await session.scalar(select(func.count()).select_from(log_model).where(log_model.file_id == file_id)) or 0
    )
    stmt = (
        select(log_model)
        .where(log_model.file_id == file_id)
        .order_by(log_model.created_at.desc(), log_model.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.execute(stmt)).scalars()), total


def _dict_values(dicts: Mapping[str, Sequence[str]] | None, key: str) -> list[str]:
    if dicts is not None and key in dicts:
        return list(dicts[key])
    return list(DEFAULT_THINKTANK_DICTS[key])


async def list_options(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    dicts: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    raw = await preview_options(session, spec.option_columns())
    for field in spec.pipe_fields:
        if field in raw:
            raw[field] = {
                "items": expand_pipe_options(raw[field].get("items") or []),
                "truncated": bool(raw[field].get("truncated", False)),
            }
    for field, dict_key in spec.codebook_option_map.items():
        entry = raw.get(field) or {}
        raw[field] = {
            "items": merge_unique(_dict_values(dicts, dict_key), entry.get("items") or []),
            "truncated": bool(entry.get("truncated", False)),
        }
    for field, static_vals in spec.static_options.items():
        entry = raw.get(field) or {}
        raw[field] = {
            "items": merge_unique(static_vals, entry.get("items") or []),
            "truncated": False,
        }
    return {"options": raw}


async def search_option_values(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    field: str,
    keyword: str | None,
    dicts: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    q = (keyword or "").strip().lower()
    option_cols = spec.option_columns()
    if field in spec.static_options and field not in option_cols:
        return [v for v in spec.static_options[field] if not q or q in v.lower()][:SEARCH_LIMIT]
    if field not in option_cols:
        raise KeyError(field)

    db_matches = await search_options(session, option_cols, field=field, keyword=keyword, limit=SEARCH_LIMIT)
    if field in spec.pipe_fields:
        db_matches = [item for item in expand_pipe_options(db_matches) if not q or q in item.lower()]

    if dict_key := spec.codebook_option_map.get(field):
        merged = merge_unique(_dict_values(dicts, dict_key), db_matches)
        return [v for v in merged if not q or q in v.lower()][:SEARCH_LIMIT]
    if static_vals := spec.static_options.get(field):
        merged = merge_unique(static_vals, db_matches)
        return [v for v in merged if not q or q in v.lower()][:SEARCH_LIMIT]
    return db_matches[:SEARCH_LIMIT]
