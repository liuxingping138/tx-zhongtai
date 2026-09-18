from __future__ import annotations

import uuid
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook, parse_sheet
from app.core.clock import utcnow
from app.domain.fields import BASE_TAG_COLUMNS
from app.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash
from app.repositories import base_tags as repo


def _to_out(row: BaseTag) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = row.created_at.isoformat()
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = row.updated_at.isoformat()
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


async def import_base_tags(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, int]:
    parsed = parse_sheet(content, BASE_TAG_COLUMNS, sheet_name="政策基础信息表数据导出")
    inserted = 0
    skipped = 0
    now = utcnow()
    seen = await repo.list_hashes(session)
    for item in parsed:
        values = _values(item)
        if not values["policy_name"]:
            skipped += 1
            continue
        digest = content_hash(values, BASE_TAG_FIELDS)
        if digest in seen:
            skipped += 1
            continue
        seen.add(digest)
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
        extra={"inserted": inserted, "skipped": skipped},
    )
    return {"inserted": inserted, "updated": 0, "skipped": skipped, "total": len(parsed)}


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
