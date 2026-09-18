from __future__ import annotations

import uuid
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook, parse_sheet
from app.core.clock import utcnow
from app.domain.fields import SCENARIO_COLUMNS
from app.domain.models import SCENARIO_FIELDS, Scenario, content_hash
from app.repositories import scenarios as repo


def _to_out(row: Scenario) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = row.created_at.isoformat()
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = row.updated_at.isoformat()
    data["updated_by_name"] = row.updated_by_name
    return data


def _apply(row: Scenario, data: dict[str, str]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field in SCENARIO_FIELDS:
        if field not in data:
            continue
        new = (data[field] or "").strip()
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if changes:
        row.refresh_hash()
    return changes


async def list_scenarios(
    session: AsyncSession,
    *,
    industry_scenario_code: str | None,
    industry_l1: str | None,
    scenario_tag: str | None,
    customer_group_name: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        industry_scenario_code=industry_scenario_code,
        industry_l1=industry_l1,
        scenario_tag=scenario_tag,
        customer_group_name=customer_group_name,
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def get_scenario(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("场景码表记录不存在")
    return _to_out(row)


async def create_scenario(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    values = {field: (data.get(field) or "").strip() for field in SCENARIO_FIELDS}
    digest = content_hash(values, SCENARIO_FIELDS)
    if await repo.get_by_hash(session, digest):
        raise ApiError("已存在完全相同的场景记录", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = Scenario(
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
        event_type="codebook.scenario.created",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes={"industry_scenario_code": row.industry_scenario_code, "scenario_tag": row.scenario_tag},
    )
    return _to_out(row)


async def update_scenario(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("场景码表记录不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    payload = {field: str(data.get(field, getattr(row, field) or "")) for field in SCENARIO_FIELDS}
    digest = content_hash({k: payload[k].strip() for k in SCENARIO_FIELDS}, SCENARIO_FIELDS)
    existing = await repo.get_by_hash(session, digest)
    if existing and existing.id != row.id:
        raise ApiError("已存在完全相同的场景记录", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes = _apply(row, payload)
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="codebook.scenario.updated",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def import_scenarios(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, int]:
    parsed = parse_sheet(content, SCENARIO_COLUMNS)
    inserted = 0
    skipped = 0
    now = utcnow()
    for item in parsed:
        values = {field: (item.get(field) or "").strip() for field in SCENARIO_FIELDS}
        digest = content_hash(values, SCENARIO_FIELDS)
        if await repo.get_by_hash(session, digest):
            skipped += 1
            continue
        session.add(
            Scenario(
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
        event_type="codebook.scenario.imported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"inserted": inserted, "skipped": skipped},
    )
    return {"inserted": inserted, "updated": 0, "skipped": skipped, "total": len(parsed)}


async def export_scenarios(session: AsyncSession, actor: Actor) -> bytes:
    rows = [_to_out(item) for item in await repo.list_all(session)]
    await enqueue_event(
        session,
        event_type="codebook.scenario.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return build_workbook(SCENARIO_COLUMNS, rows, sheet_name="行业场景字典表")
