from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook, encode_skipped_file, parse_sheet
from app.core.clock import format_beijing, utcnow
from app.domain.fields import BASE_TAG_COLUMNS
from app.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash
from app.repositories import base_tags as repo
from app.repositories import options as options_repo


def _to_out(row: BaseTag) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = format_beijing(row.created_at)
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = format_beijing(row.updated_at)
    data["updated_by_name"] = row.updated_by_name
    return data


def _values(data: dict[str, str]) -> dict[str, str]:
    return {field: (data.get(field) or "").strip() for field in BASE_TAG_FIELDS}


async def list_base_tags(
    session: AsyncSession,
    *,
    policy_name: str | None,
    province_name: str | None,
    policy_types: str | None,
    is_penetrate: str | None,
    need_interpret: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        policy_name=policy_name,
        province_name=province_name,
        policy_types=policy_types,
        is_penetrate=is_penetrate,
        need_interpret=need_interpret,
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_base_tag_options(session: AsyncSession) -> dict[str, list[str]]:
    return await options_repo.base_tag_options(session)


async def get_base_tag(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策基础标签不存在")
    return _to_out(row)


async def create_base_tag(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    values = _values(data)
    if not values["policy_name"]:
        raise ApiError("政策名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    digest = content_hash(values, BASE_TAG_FIELDS)
    if await repo.get_by_hash(session, digest):
        raise ApiError("已存在完全相同的政策基础标签", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = BaseTag(
        content_hash=digest,
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
        event_type="policy.base_tag.created",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes={"policy_name": row.policy_name},
    )
    return _to_out(row)


async def update_base_tag(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策基础标签不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    values = _values({field: str(data.get(field, getattr(row, field) or "")) for field in BASE_TAG_FIELDS})
    digest = content_hash(values, BASE_TAG_FIELDS)
    existing = await repo.get_by_hash(session, digest)
    if existing and existing.id != row.id:
        raise ApiError("已存在完全相同的政策基础标签", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if not changes:
        return _to_out(row)
    row.refresh_hash()
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="policy.base_tag.updated",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


def _has_any_area_code(item: dict[str, str]) -> bool:
    return bool((item.get("province_code") or "").strip() or (item.get("city_code") or "").strip())


async def import_base_tags(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = parse_sheet(content, BASE_TAG_COLUMNS, sheet_name="政策基础信息表数据导出")
    db_hashes = await repo.list_hashes(session)
    staged: list[tuple[dict[str, str], str]] = []
    for item in parsed:
        values = _values(item)
        digest = content_hash(values, BASE_TAG_FIELDS)
        staged.append((values, digest))
    file_hashes = Counter(item[1] for item in staged)
    marked: list[dict[str, str]] = []
    blocked = 0
    for values, digest in staged:
        reasons: list[str] = []
        if not _has_any_area_code(values):
            reasons.append("省市区编码为空")
        if not values["policy_name"]:
            reasons.append("政策名称为空")
        if digest in db_hashes:
            reasons.append("内容已存在")
        if file_hashes[digest] > 1:
            reasons.append("文件内重复")
        marked.append({**values, "skip_reason": "；".join(reasons) if reasons else "通过"})
        if reasons:
            blocked += 1
    if blocked:
        return {
            "inserted": 0,
            "updated": 0,
            "skipped": blocked,
            "total": len(parsed),
            "rejected": True,
            "skipped_file": encode_skipped_file(BASE_TAG_COLUMNS, marked),
        }
    inserted = 0
    now = utcnow()
    for values, digest in staged:
        session.add(
            BaseTag(
                content_hash=digest,
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
        event_type="policy.base_tag.imported",
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


async def export_base_tags(session: AsyncSession, actor: Actor) -> bytes:
    rows = [_to_out(item) for item in await repo.list_all(session)]
    await enqueue_event(
        session,
        event_type="policy.base_tag.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return build_workbook(BASE_TAG_COLUMNS, rows, sheet_name="政策基础信息表")
