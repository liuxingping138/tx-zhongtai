"""智库专属 6 张码表应用层：查询、筛选项、增删改、导入导出、内部全量聚合与幂等初始化。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters, FilterValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.core.config import get_settings
from app.domain.models import ThinktankDict
from app.domain.thinktank_dicts import (
    THINKTANK_DICT_BY_TYPE,
    THINKTANK_DICT_SPECS,
    ThinktankDictSpec,
    stable_seed_id,
)
from app.repositories import options as options_repo
from app.repositories import thinktank_dicts as repo

THINKTANK_DICT_LENGTHS = string_lengths(ThinktankDict)


def _spec_for(dict_type: str) -> ThinktankDictSpec:
    spec = THINKTANK_DICT_BY_TYPE.get(dict_type)
    if spec is None:
        raise NotFoundError(f"未知智库码表类型: {dict_type}")
    return spec


def _to_out(row: ThinktankDict) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "dict_type": row.dict_type,
        "name": row.name,
        "sort_order": row.sort_order,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


def _overlong(spec: ThinktankDictSpec, name: str) -> list[str]:
    return overlong_reasons({"name": name}, spec.columns, THINKTANK_DICT_LENGTHS)


def _validate_name(spec: ThinktankDictSpec, raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ApiError(f"{spec.label}不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if reasons := _overlong(spec, name):
        raise ApiError("、".join(reasons), code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return name


async def list_dicts(
    session: AsyncSession,
    dict_type: str,
    *,
    keyword: FilterValue,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    _spec_for(dict_type)
    items, total = await repo.list_items(
        session, dict_type, filters={"keyword": keyword}, page=page, page_size=page_size
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_dict_options(session: AsyncSession, dict_type: str) -> dict[str, Any]:
    _spec_for(dict_type)
    return await options_repo.thinktank_dict_options(session, dict_type)


async def search_dict_options(session: AsyncSession, dict_type: str, *, field: str, keyword: str | None) -> list[str]:
    _spec_for(dict_type)
    return await options_repo.search_thinktank_dict_options(session, dict_type, field=field, keyword=keyword)


async def create_dict(session: AsyncSession, actor: Actor, dict_type: str, data: dict[str, Any]) -> dict[str, Any]:
    spec = _spec_for(dict_type)
    name = _validate_name(spec, data.get("name"))
    if await repo.get_by_name(session, dict_type, name):
        raise ApiError(f"{spec.label}已存在", code=ErrorCode.DUPLICATE, http_status=409)
    raw_order = data.get("sort_order")
    sort_order = int(raw_order) if raw_order is not None else 0
    now = utcnow()
    row = ThinktankDict(
        dict_type=dict_type,
        name=name,
        sort_order=sort_order,
        version=1,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
    )
    session.add(row)
    await session.flush()
    await enqueue_event(
        session,
        event_type=f"codebook.thinktank.{dict_type}.created",
        actor=actor,
        target_id=str(row.id),
        changes={"name": row.name, "sort_order": row.sort_order},
    )
    return _to_out(row)


async def update_dict(
    session: AsyncSession, actor: Actor, dict_type: str, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    spec = _spec_for(dict_type)
    row = await repo.get_for_update(session, dict_type, item_id)
    if row is None:
        raise NotFoundError(f"{spec.label}不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()

    changes: dict[str, Any] = {}
    if "name" in data and data["name"] is not None:
        name = _validate_name(spec, data["name"])
        if name != row.name:
            existing = await repo.get_by_name(session, dict_type, name)
            if existing and existing.id != row.id:
                raise ApiError(f"{spec.label}已存在", code=ErrorCode.DUPLICATE, http_status=409)
            changes["name"] = {"from": row.name, "to": name}
            row.name = name

    if "sort_order" in data and data["sort_order"] is not None:
        new_order = int(data["sort_order"])
        if new_order != row.sort_order:
            changes["sort_order"] = {"from": row.sort_order, "to": new_order}
            row.sort_order = new_order

    if not changes:
        return _to_out(row)

    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type=f"codebook.thinktank.{dict_type}.updated",
        actor=actor,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def delete_dict(session: AsyncSession, actor: Actor, dict_type: str, item_id: uuid.UUID) -> dict[str, bool]:
    spec = _spec_for(dict_type)
    row = await repo.get_for_update(session, dict_type, item_id)
    if row is None:
        raise NotFoundError(f"{spec.label}不存在")
    target_id = str(row.id)
    old_name = row.name
    await repo.delete_item(session, row)
    await session.flush()
    await enqueue_event(
        session,
        event_type=f"codebook.thinktank.{dict_type}.deleted",
        actor=actor,
        target_id=target_id,
        changes={"name": old_name},
    )
    return {"deleted": True}


async def _assert_exportable(session: AsyncSession, dict_type: str, filters: Filters) -> None:
    limit = get_settings().export_max_rows
    total = await repo.count_filtered(session, dict_type, filters)
    if total > limit:
        scope = "筛选结果" if any(filters.values()) else "本表"
        raise ApiError(
            f"{scope}共 {total} 条，超过单次导出上限 {limit} 条，请先缩小筛选范围后再导出。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )


async def export_dicts(session: AsyncSession, actor: Actor, dict_type: str, filters: Filters) -> bytes:
    spec = _spec_for(dict_type)
    await _assert_exportable(session, dict_type, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, dict_type, filters)]
    await enqueue_event(
        session,
        event_type=f"codebook.thinktank.{dict_type}.exported",
        actor=actor,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(spec.columns, rows, sheet_name=spec.title)


async def import_dicts(session: AsyncSession, actor: Actor, dict_type: str, content: bytes) -> dict[str, Any]:
    spec = _spec_for(dict_type)
    parsed = await parse_sheet_async(content, spec.import_columns, subject=spec.title)
    candidate_names = [item.get("name", "").strip() for item in parsed]
    existing = await repo.existing_names(session, dict_type, candidate_names)
    seen: set[str] = set()
    inserted = 0
    skipped_rows: list[dict[str, str]] = []
    now = utcnow()
    for item in parsed:
        name = item.get("name", "").strip()
        if not name:
            skipped_rows.append({"name": "", "skip_reason": f"{spec.label}为空"})
            continue
        if reasons := _overlong(spec, name):
            skipped_rows.append({"name": name, "skip_reason": "、".join(reasons)})
            continue
        if name in existing or name in seen:
            skipped_rows.append({"name": name, "skip_reason": f"{spec.label}已存在"})
            continue
        seen.add(name)
        session.add(
            ThinktankDict(
                dict_type=dict_type,
                name=name,
                sort_order=0,
                version=1,
                created_at=now,
                created_by_id=actor.id,
                created_by_name=actor.name,
                updated_at=now,
                updated_by_id=actor.id,
                updated_by_name=actor.name,
            )
        )
        inserted += 1
    await session.flush()
    await enqueue_event(
        session,
        event_type=f"codebook.thinktank.{dict_type}.imported",
        actor=actor,
        extra={"inserted": inserted, "updated": 0, "skipped": len(skipped_rows)},
    )
    return {
        "inserted": inserted,
        "updated": 0,
        "skipped": len(skipped_rows),
        "total": len(parsed),
        "skipped_file": await encode_skipped_file_async(spec.columns, skipped_rows),
    }


async def get_all_thinktank_dicts(session: AsyncSession) -> dict[str, list[str]]:
    return await repo.list_all_grouped(session)


async def seed_thinktank_dicts(session: AsyncSession) -> int:
    """幂等初始化 6 张智库专属码表（ON CONFLICT DO NOTHING），可重复安全调用。"""

    now = utcnow()
    rows = [
        {
            "id": stable_seed_id(spec.dict_type, name),
            "dict_type": spec.dict_type,
            "name": name,
            "sort_order": idx,
            "version": 1,
            "created_at": now,
            "created_by_id": "system",
            "created_by_name": "系统初始化",
            "updated_at": now,
            "updated_by_id": "system",
            "updated_by_name": "系统初始化",
        }
        for spec in THINKTANK_DICT_SPECS
        for idx, name in enumerate(spec.seed_values, start=1)
    ]
    return await repo.insert_seed_rows(session, rows)
