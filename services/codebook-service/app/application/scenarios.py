from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters, FilterValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.core.config import get_settings
from app.domain.fields import SCENARIO_COLUMNS
from app.domain.models import SCENARIO_FIELDS, Scenario, content_hash
from app.repositories import options as options_repo
from app.repositories import scenarios as repo


def _to_out(row: Scenario) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = format_beijing(row.created_at)
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = format_beijing(row.updated_at)
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
    industry_scenario_code: FilterValue,
    industry_l1: FilterValue,
    scenario_tag: FilterValue,
    customer_group_name: FilterValue,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        filters={
            "industry_scenario_code": industry_scenario_code,
            "industry_l1": industry_l1,
            "scenario_tag": scenario_tag,
            "customer_group_name": customer_group_name,
        },
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_scenario_options(session: AsyncSession) -> dict[str, Any]:
    return await options_repo.scenario_options(session)


async def search_scenario_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(session, options_repo.SCENARIO_OPTION_COLUMNS, field=field, keyword=keyword)


async def get_scenario(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("行业场景码表记录不存在")
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
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("行业场景码表记录不存在")
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


async def import_scenarios(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, SCENARIO_COLUMNS, subject="码表")
    inserted = 0
    skipped_rows: list[dict[str, str]] = []
    now = utcnow()
    for item in parsed:
        values = {field: (item.get(field) or "").strip() for field in SCENARIO_FIELDS}
        digest = content_hash(values, SCENARIO_FIELDS)
        if await repo.get_by_hash(session, digest):
            skipped_rows.append({**values, "skip_reason": "内容已存在"})
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
        extra={"inserted": inserted, "skipped": len(skipped_rows)},
    )
    return {
        "inserted": inserted,
        "updated": 0,
        "skipped": len(skipped_rows),
        "total": len(parsed),
        "skipped_file": await encode_skipped_file_async(SCENARIO_COLUMNS, skipped_rows),
    }


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


async def export_scenarios(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="codebook.scenario.exported",
        actor_id=actor.id,
        actor_name=actor.name,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(SCENARIO_COLUMNS, rows, sheet_name="行业场景字典表")
