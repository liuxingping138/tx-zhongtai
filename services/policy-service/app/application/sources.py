from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from app.application.region import digits_only, make_internal_id, next_site_code, normalize_region, site_code_prefix
from app.core.clock import format_beijing, utcnow
from app.core.config import get_settings
from app.domain.fields import SOURCE_COLUMNS
from app.domain.filters import Filters
from app.domain.models import SOURCE_FIELDS, Source
from app.repositories import options as options_repo
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
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
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


def _has_any_area_code(item: dict[str, str]) -> bool:
    return bool(
        (item.get("province_code") or "").strip()
        or (item.get("city_code") or "").strip()
        or (item.get("district_code") or "").strip()
    )


async def _allocate_site_code(
    session: AsyncSession, province_code: str, city_code: str, district_code: str
) -> str:
    prefix = site_code_prefix(province_code, city_code, district_code)
    existing = await repo.list_site_codes_for_district(session, prefix)
    return next_site_code(prefix, existing)


async def list_sources(
    session: AsyncSession,
    *,
    site_name: str | None,
    province_name: str | None,
    city_name: str | None,
    tag: str | None,
    site_code: str | None,
    crawl_priority: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        filters={
        "site_name": site_name,
        "province_name": province_name,
        "city_name": city_name,
        "tag": tag,
        "site_code": site_code,
        "crawl_priority": crawl_priority,
        },
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_source_options(session: AsyncSession) -> dict[str, Any]:
    return await options_repo.source_options(session)


async def get_source(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    return _to_out(row)


async def create_source(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    raw = {field: (data.get(field) or "").strip() for field in SOURCE_FIELDS}
    if not raw["site_name"]:
        raise ApiError("网站名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not _has_any_area_code(raw):
        raise ApiError("省市区编码不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    values = _normalized_values(raw)
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    if await repo.get_by_internal_id(session, internal_id):
        raise ApiError("已存在相同的内部唯一 id", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    site_code = await _allocate_site_code(
        session, values["province_code"], values["city_code"], values["district_code"]
    )
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
    raw = {field: str(data.get(field, getattr(row, field) or "")).strip() for field in SOURCE_FIELDS}
    if not raw["site_name"]:
        raise ApiError("网站名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not _has_any_area_code(raw):
        raise ApiError("省市区编码不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    values = _normalized_values(raw)
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


async def import_sources(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, SOURCE_COLUMNS)
    db_internal = await repo.list_internal_ids(session)
    db_site = await repo.list_site_codes(session)
    staged: list[tuple[dict[str, str], str, str, str]] = []
    for item in parsed:
        values = {field: (item.get(field) or "").strip() for field in SOURCE_FIELDS}
        internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
        site_code = (item.get("site_code") or "").strip()
        resolve_reason = (item.get("skip_reason") or "").strip()
        staged.append((values, internal_id, site_code, resolve_reason))
    file_internal = Counter(item[1] for item in staged)
    file_site = Counter(item[2] for item in staged if item[2])
    marked: list[dict[str, str]] = []
    blocked = 0
    for values, internal_id, site_code, resolve_reason in staged:
        reasons: list[str] = []
        if not site_code and not _has_any_area_code(values):
            if resolve_reason and resolve_reason != "通过":
                reasons.append(resolve_reason)
            else:
                reasons.append("省市区编码为空")
        if not values["site_name"]:
            reasons.append("网站名称为空")
        if internal_id in db_internal:
            reasons.append("内部唯一id已存在")
        if file_internal[internal_id] > 1:
            reasons.append("网站名称+省份+地市+标签重复")
        if site_code:
            digits = digits_only(site_code)
            if not digits or digits != site_code or len(site_code) > 16:
                reasons.append("网站编码不合法")
            elif site_code in db_site:
                reasons.append("网站编码已存在")
            if file_site[site_code] > 1:
                reasons.append("文件内网站编码重复")
        marked.append({**values, "site_code": site_code, "skip_reason": "；".join(reasons) if reasons else "通过"})
        if reasons:
            blocked += 1
    if blocked:
        return {
            "inserted": 0,
            "updated": 0,
            "skipped": blocked,
            "total": len(parsed),
            "rejected": True,
            "skipped_file": await encode_skipped_file_async(SOURCE_COLUMNS, marked),
        }
    inserted = 0
    now = utcnow()
    seen_site = set(db_site)
    seen_site.update(item[2] for item in staged if item[2])
    for values, internal_id, site_code, _reason in staged:
        normalized = _normalized_values(values)
        if not site_code:
            prefix = site_code_prefix(
                normalized["province_code"], normalized["city_code"], normalized["district_code"]
            )
            site_code = next_site_code(prefix, list(seen_site))
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
                **normalized,
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
        extra={"inserted": inserted, "skipped": 0},
    )
    return {
        "inserted": inserted,
        "updated": 0,
        "skipped": 0,
        "total": len(parsed),
        "skipped_file": None,
    }


async def purge_sources(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    deleted = await repo.delete_all(session)
    await enqueue_event(
        session,
        event_type="policy.source.purged",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"deleted": deleted},
    )
    return {"deleted": deleted}


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


async def export_sources(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="policy.source.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(SOURCE_COLUMNS, rows, sheet_name="网站编码")
