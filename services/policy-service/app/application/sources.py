from __future__ import annotations

import uuid
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook, parse_sheet
from app.application.region import make_internal_id, next_site_code, normalize_region
from app.core.clock import utcnow
from app.domain.fields import SOURCE_COLUMNS
from app.domain.models import SOURCE_FIELDS, Source
from app.repositories import sources as repo


def _to_out(row: Source) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "internal_id": row.internal_id,
        "site_code": row.site_code,
        "province_name": row.province_name,
        "province_code": row.province_code,
        "city_name": row.city_name,
        "city_code": row.city_code,
        "district_name": row.district_name,
        "district_code": row.district_code,
        "site_name": row.site_name,
        "crawl_priority": row.crawl_priority,
        "url": row.url,
        "tag": row.tag,
        "data_type": row.data_type,
        "department": row.department,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "created_by_name": row.created_by_name,
        "updated_at": row.updated_at.isoformat(),
        "updated_by_name": row.updated_by_name,
    }


def _normalized_values(data: dict[str, str]) -> dict[str, str]:
    values = {field: (data.get(field) or "").strip() for field in SOURCE_FIELDS}
    province_code, city_code, district_code = normalize_region(
        values["province_code"], values["city_code"], values["district_code"]
    )
    values["province_code"] = province_code
    values["city_code"] = city_code
    values["district_code"] = district_code
    return values


async def _allocate_site_code(session: AsyncSession, district_code: str) -> str:
    existing = await repo.list_site_codes_for_district(session, district_code)
    return next_site_code(district_code, existing)


async def list_sources(
    session: AsyncSession,
    *,
    site_name: str | None,
    province_name: str | None,
    city_name: str | None,
    tag: str | None,
    site_code: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        site_name=site_name,
        province_name=province_name,
        city_name=city_name,
        tag=tag,
        site_code=site_code,
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def get_source(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    return _to_out(row)


async def create_source(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    values = _normalized_values(data)
    if not values["site_name"]:
        raise ApiError("网站名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    if await repo.get_by_internal_id(session, internal_id):
        raise ApiError("已存在相同的内部唯一 id", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    site_code = await _allocate_site_code(session, values["district_code"])
    if await repo.get_by_site_code(session, site_code):
        raise ApiError("网站编码冲突，请重试", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = Source(
        internal_id=internal_id,
        site_code=site_code,
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
        event_type="policy.source.created",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes={"site_code": site_code, "site_name": row.site_name},
    )
    return _to_out(row)


async def update_source(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    values = _normalized_values({field: str(data.get(field, getattr(row, field) or "")) for field in SOURCE_FIELDS})
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    existing = await repo.get_by_internal_id(session, internal_id)
    if existing and existing.id != row.id:
        raise ApiError("已存在相同的内部唯一 id", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if row.internal_id != internal_id:
        changes["internal_id"] = {"from": row.internal_id, "to": internal_id}
        row.internal_id = internal_id
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="policy.source.updated",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def import_sources(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, int]:
    parsed = parse_sheet(content, SOURCE_COLUMNS, sheet_name="网站-0430-编码")
    inserted = 0
    skipped = 0
    now = utcnow()
    seen_internal = await repo.list_internal_ids(session)
    seen_site = await repo.list_site_codes(session)
    for item in parsed:
        values = _normalized_values(item)
        if not values["site_name"]:
            skipped += 1
            continue
        internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
        site_code = (item.get("site_code") or "").strip()
        if internal_id in seen_internal:
            skipped += 1
            continue
        if site_code and site_code in seen_site:
            skipped += 1
            continue
        if not site_code:
            site_code = await _allocate_site_code(session, values["district_code"])
        seen_internal.add(internal_id)
        seen_site.add(site_code)
        session.add(
            Source(
                internal_id=internal_id,
                site_code=site_code,
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
        event_type="policy.source.imported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"inserted": inserted, "skipped": skipped},
    )
    return {"inserted": inserted, "updated": 0, "skipped": skipped, "total": len(parsed)}


async def export_sources(session: AsyncSession, actor: Actor) -> bytes:
    rows = [_to_out(item) for item in await repo.list_all(session)]
    await enqueue_event(
        session,
        event_type="policy.source.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return build_workbook(SOURCE_COLUMNS, rows, sheet_name="网站编码")
