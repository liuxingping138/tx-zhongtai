from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters, FilterValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.policy.application.region import make_policy_uid, make_relation_key
from app.policy.domain.fields import DATA_STATUS_CHOICES, DATA_STATUS_PENDING, INTERPRETATION_COLUMNS
from app.policy.domain.models import INTERPRETATION_WRITE_FIELDS, Interpretation
from app.policy.repositories import interpretations as repo
from app.policy.repositories import options as options_repo


def _to_out(row: Interpretation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "record_id": row.record_id,
        "tenant_id": row.tenant_id,
        "policy_uid": row.policy_uid,
        "policy_title": row.policy_title,
        "industry_scenario_code": row.industry_scenario_code,
        "industry_code": row.industry_code,
        "industry_l1": row.industry_l1,
        "industry_l2": row.industry_l2,
        "industry_l3": row.industry_l3,
        "scenario_code": row.scenario_code,
        "scenario_l1_name": row.scenario_l1_name,
        "scenario_l2_name": row.scenario_l2_name,
        "scenario_l3_name": row.scenario_l3_name,
        "target_customers": row.target_customers,
        "relation_key": row.relation_key,
        "opportunity_type": row.opportunity_type,
        "policy_summary": row.policy_summary,
        "has_subsidy": row.has_subsidy,
        "subsidy_content": row.subsidy_content,
        "market_opportunity": row.market_opportunity,
        "info_level": row.info_level,
        "is_new_scenario": row.is_new_scenario,
        "new_scenario_level": row.new_scenario_level,
        "data_status": row.data_status,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


def _values(data: dict[str, str]) -> dict[str, str]:
    values = {field: (data.get(field) or "").strip() for field in INTERPRETATION_WRITE_FIELDS}
    if not values["policy_uid"]:
        values["policy_uid"] = make_policy_uid(values["policy_title"])
    # 没填数据状态（新增、旧模板导入）一律按待验证入库，不留空值。
    if not values["data_status"]:
        values["data_status"] = DATA_STATUS_PENDING
    values["relation_key"] = make_relation_key(
        values["policy_uid"], values["industry_scenario_code"], values["opportunity_type"]
    )
    return values


def _data_status_error(values: dict[str, str]) -> str | None:
    """数据状态只允许固定两项，写入前统一校验。"""

    if values["data_status"] in DATA_STATUS_CHOICES:
        return None
    return f"数据状态只能是{'、'.join(DATA_STATUS_CHOICES)}"


async def list_interpretations(
    session: AsyncSession,
    *,
    policy_title: FilterValue,
    industry_scenario_code: FilterValue,
    industry_l1: FilterValue,
    scenario_l1_name: FilterValue,
    opportunity_type: FilterValue,
    is_new_scenario: FilterValue,
    new_scenario_level: FilterValue,
    info_level: FilterValue,
    data_status: FilterValue,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        filters={
            "policy_title": policy_title,
            "industry_scenario_code": industry_scenario_code,
            "industry_l1": industry_l1,
            "scenario_l1_name": scenario_l1_name,
            "opportunity_type": opportunity_type,
            "is_new_scenario": is_new_scenario,
            "new_scenario_level": new_scenario_level,
            "info_level": info_level,
            "data_status": data_status,
        },
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_interpretation_options(session: AsyncSession) -> dict[str, Any]:
    return await options_repo.interpretation_options(session)


async def search_interpretation_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(session, options_repo.INTERPRETATION_OPTION_COLUMNS, field=field, keyword=keyword)


async def get_interpretation(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    return _to_out(row)


async def create_interpretation(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    values = _values(data)
    if not values["policy_title"]:
        raise ApiError("政策原文名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if message := _data_status_error(values):
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if await repo.get_by_relation_key(session, values["relation_key"]):
        raise ApiError("已存在相同的关联主键", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    item_id = uuid.uuid4()
    row = Interpretation(
        id=item_id,
        record_id=str(item_id),
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
        event_type="policy.interpretation.created",
        actor=actor,
        target_id=str(row.id),
        changes={"policy_title": row.policy_title, "relation_key": row.relation_key},
    )
    return _to_out(row)


async def update_interpretation(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    payload = {field: str(data.get(field, getattr(row, field) or "")) for field in INTERPRETATION_WRITE_FIELDS}
    # 请求没带数据状态时沿用原值，避免旧客户端保存一次就把「人工验证」冲回「待验证」。
    if not payload["data_status"].strip():
        payload["data_status"] = row.data_status
    values = _values(payload)
    if not values["policy_title"]:
        raise ApiError("政策原文名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if message := _data_status_error(values):
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    existing = await repo.get_by_relation_key(session, values["relation_key"])
    if existing and existing.id != row.id:
        raise ApiError("已存在相同的关联主键", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="policy.interpretation.updated",
        actor=actor,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def import_interpretations(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, INTERPRETATION_COLUMNS, subject="政策")
    inserted = 0
    skipped_rows: list[dict[str, str]] = []
    now = utcnow()
    seen = await repo.list_relation_keys(session)
    for item in parsed:
        values = _values(item)
        if not values["policy_title"]:
            skipped_rows.append({**values, "skip_reason": "政策原文名称为空"})
            continue
        if message := _data_status_error(values):
            skipped_rows.append({**values, "skip_reason": message})
            continue
        if values["relation_key"] in seen:
            skipped_rows.append({**values, "skip_reason": "关联主键已存在"})
            continue
        seen.add(values["relation_key"])
        item_id = uuid.uuid4()
        session.add(
            Interpretation(
                id=item_id,
                record_id=str(item_id),
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
        event_type="policy.interpretation.imported",
        actor=actor,
        extra={"inserted": inserted, "skipped": len(skipped_rows)},
    )
    return {
        "inserted": inserted,
        "updated": 0,
        "skipped": len(skipped_rows),
        "total": len(parsed),
        "skipped_file": await encode_skipped_file_async(INTERPRETATION_COLUMNS, skipped_rows),
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


async def export_interpretations(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="policy.interpretation.exported",
        actor=actor,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(INTERPRETATION_COLUMNS, rows, sheet_name="政策解读表")
