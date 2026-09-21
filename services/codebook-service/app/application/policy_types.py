from __future__ import annotations

import uuid
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.actors import Actor
from app.application.audit_emit import enqueue_event
from app.application.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from app.core.clock import format_beijing, utcnow
from app.core.config import get_settings
from app.domain.fields import POLICY_TYPE_COLUMNS
from app.domain.models import PolicyType
from app.repositories import options as options_repo
from app.repositories import policy_types as repo


def _to_out(row: PolicyType) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "seq_no": row.seq_no,
        "type_name": row.type_name,
        "definition": row.definition,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


def _apply_fields(row: PolicyType, data: dict[str, str]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field in ("seq_no", "type_name", "definition"):
        if field not in data:
            continue
        new = (data[field] or "").strip()
        old = getattr(row, field)
        if old != new:
            changes[field] = {"from": old, "to": new}
            setattr(row, field, new)
    return changes


async def list_policy_types(session: AsyncSession, *, keyword: str | None, page: int, page_size: int) -> dict[str, Any]:
    items, total = await repo.list_items(session, keyword=keyword, page=page, page_size=page_size)
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_policy_type_options(session: AsyncSession) -> dict[str, list[str]]:
    return await options_repo.policy_type_options(session)


async def create_policy_type(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    type_name = (data.get("type_name") or "").strip()
    if not type_name:
        raise ApiError("政策类型不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if await repo.get_by_name(session, type_name):
        raise ApiError("政策类型已存在", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = PolicyType(
        seq_no=(data.get("seq_no") or "").strip(),
        type_name=type_name,
        definition=(data.get("definition") or "").strip(),
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
        event_type="codebook.policy_type.created",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes={"type_name": row.type_name},
    )
    return _to_out(row)


async def update_policy_type(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策类型不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    type_name = (data.get("type_name") or row.type_name).strip()
    if type_name != row.type_name:
        existing = await repo.get_by_name(session, type_name)
        if existing and existing.id != row.id:
            raise ApiError("政策类型已存在", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes = _apply_fields(row, {k: str(data.get(k, getattr(row, k))) for k in ("seq_no", "type_name", "definition")})
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="codebook.policy_type.updated",
        actor_id=actor.id,
        actor_name=actor.name,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def import_policy_types(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, POLICY_TYPE_COLUMNS)
    inserted = 0
    updated = 0
    skipped_rows: list[dict[str, str]] = []
    now = utcnow()
    for item in parsed:
        type_name = item.get("type_name", "").strip()
        if not type_name:
            skipped_rows.append({**item, "skip_reason": "政策类型为空"})
            continue
        row = await repo.get_by_name(session, type_name)
        if row is None:
            session.add(
                PolicyType(
                    seq_no=item.get("seq_no", "").strip(),
                    type_name=type_name,
                    definition=item.get("definition", "").strip(),
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
            continue
        changed = _apply_fields(row, item)
        if not changed:
            skipped_rows.append({**item, "skip_reason": "内容无变化"})
            continue
        row.version += 1
        row.updated_at = now
        row.updated_by_id = actor.id
        row.updated_by_name = actor.name
        updated += 1
    await session.flush()
    await enqueue_event(
        session,
        event_type="codebook.policy_type.imported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"inserted": inserted, "updated": updated, "skipped": len(skipped_rows)},
    )
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": len(skipped_rows),
        "total": len(parsed),
        "skipped_file": await encode_skipped_file_async(POLICY_TYPE_COLUMNS, skipped_rows),
    }


async def _assert_exportable(session: AsyncSession) -> None:
    """导出前校验行数上限。

    导出是整表读进内存再生成 Excel，没有上限时大表会把服务撑爆。
    上限由 ``export_max_rows`` 配置，默认 10 万行。
    """

    limit = get_settings().export_max_rows
    total = await repo.count_all(session)
    if total > limit:
        raise ApiError(
            f"本表共 {total} 条，超过单次导出上限 {limit} 条，请联系管理员调整上限后再试。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )


async def export_policy_types(session: AsyncSession, actor: Actor) -> bytes:
    await _assert_exportable(session)
    rows = []
    for item in await repo.list_all(session):
        rows.append(_to_out(item) | {"seq_no": item.seq_no, "type_name": item.type_name, "definition": item.definition})
    await enqueue_event(
        session,
        event_type="codebook.policy_type.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(POLICY_TYPE_COLUMNS, rows, sheet_name="政策类型枚举值")
