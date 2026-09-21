from __future__ import annotations

import asyncio
import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.area_match import AreaSnap
from app.application.area_resolve import build_resolve_workbook
from app.application.audit_emit import enqueue_event
from app.core.config import get_settings
from app.domain.fields import AREA_CODE_COLUMNS
from app.domain.models import AREA_CODE_FIELDS, AreaCode
from app.repositories import area_codes as repo
from app.repositories import options as options_repo


def _to_out(row: AreaCode) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = format_beijing(row.created_at)
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = format_beijing(row.updated_at)
    data["updated_by_name"] = row.updated_by_name
    return data


def _values(data: dict[str, Any]) -> dict[str, str]:
    return {field: str(data.get(field) or "").strip() for field in AREA_CODE_FIELDS}


def _apply(row: AreaCode, data: dict[str, str]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field in AREA_CODE_FIELDS:
        if field not in data:
            continue
        new = data[field]
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    return changes


def _require_county_id(values: dict[str, str]) -> str:
    county_id = values["county_id"]
    if not county_id:
        raise ApiError("区县编码不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return county_id


async def list_area_codes(
    session: AsyncSession,
    *,
    prov_name: str | None,
    city_name: str | None,
    county_name: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        filters={
            "prov_name": prov_name,
            "city_name": city_name,
            "county_name": county_name,
        },
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_area_code_options(session: AsyncSession) -> dict[str, Any]:
    return await options_repo.area_code_options(session)


async def search_area_code_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(
        session, options_repo.AREA_CODE_OPTION_COLUMNS, field=field, keyword=keyword
    )


async def get_area_code(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("省市区编码记录不存在")
    return _to_out(row)


async def create_area_code(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    values = _values(data)
    county_id = _require_county_id(values)
    if await repo.get_by_county_id(session, county_id):
        raise ApiError("区县编码已存在", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = AreaCode(
        version=1,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
        **values,
    )
    session.add(row)
    await session.flush()
    await enqueue_event(
        session,
        event_type="codebook.area_code.created",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes={"county_id": row.county_id, "county_name": row.county_name},
    )
    return _to_out(row)


async def update_area_code(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("省市区编码记录不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    payload = {field: str(data.get(field, getattr(row, field) or "")).strip() for field in AREA_CODE_FIELDS}
    county_id = _require_county_id(payload)
    existing = await repo.get_by_county_id(session, county_id)
    if existing and existing.id != row.id:
        raise ApiError("区县编码已存在", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes = _apply(row, payload)
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="codebook.area_code.updated",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def import_area_codes(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, AREA_CODE_COLUMNS, subject="码表")
    return await upsert_area_code_rows(session, actor, parsed, event_type="codebook.area_code.imported")


async def upsert_area_code_rows(
    session: AsyncSession,
    actor: Actor,
    parsed: list[dict[str, str]],
    *,
    event_type: str,
) -> dict[str, Any]:
    inserted = 0
    skipped_rows: list[dict[str, str]] = []
    now = utcnow()
    for item in parsed:
        values = _values(item)
        county_id = values["county_id"]
        if not county_id:
            skipped_rows.append({**values, "skip_reason": "区县编码为空"})
            continue
        if await repo.get_by_county_id(session, county_id):
            skipped_rows.append({**values, "skip_reason": "区县编码已存在"})
            continue
        session.add(
            AreaCode(
                version=1,
                created_at=now,
                created_by_id=actor.id,
                created_by_name=actor.name,
                updated_at=now,
                updated_by_id=actor.id,
                updated_by_name=actor.name,
                **values,
            )
        )
        inserted += 1
        if inserted % 200 == 0:
            await session.flush()
    await session.flush()
    await enqueue_event(
        session,
        event_type=event_type,
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"inserted": inserted, "skipped": len(skipped_rows)},
    )
    return {
        "inserted": inserted,
        "updated": 0,
        "skipped": len(skipped_rows),
        "total": len(parsed),
        "skipped_file": await encode_skipped_file_async(AREA_CODE_COLUMNS, skipped_rows),
    }


async def resolve_area_codes(session: AsyncSession, actor: Actor, content: bytes) -> tuple[bytes, int, int]:
    catalog = [
        AreaSnap(
            prov_id=row.prov_id,
            prov_name=row.prov_name,
            city_id=row.city_id,
            city_name=row.city_name,
            county_id=row.county_id,
            county_name=row.county_name,
            alias_prov_name=row.alias_prov_name,
            alias_city_name=row.alias_city_name,
            alias_county_name=row.alias_county_name,
            city_name_short=row.city_name_short,
            county_name_short=row.county_name_short,
        )
        for row in await repo.list_all(session)  # 地区匹配需要完整码表，不受导出筛选影响
    ]
    payload, matched, unmatched = await asyncio.to_thread(build_resolve_workbook, content, catalog)
    await enqueue_event(
        session,
        event_type="codebook.area_code.resolved",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"matched": matched, "unmatched": unmatched, "total": matched + unmatched},
    )
    return payload, matched, unmatched


async def _assert_exportable(session: AsyncSession, filters: Filters) -> None:
    """导出前按当前筛选条件校验行数上限。

    导出是把结果集整个读进内存再生成 Excel，没有上限时大表会把服务撑爆。
    上限由 ``export_max_rows`` 配置，默认 10 万行；超限时提示先缩小筛选范围。
    """

    limit = get_settings().export_max_rows
    total = await repo.count_filtered(session, filters)
    if total > limit:
        scope = "筛选结果" if any(filters.values()) else "本表"
        raise ApiError(
            f"{scope}共 {total} 条，超过单次导出上限 {limit} 条，请先缩小筛选范围后再导出。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )


async def export_area_codes(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="codebook.area_code.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(AREA_CODE_COLUMNS, rows, sheet_name="省市区编码表")
