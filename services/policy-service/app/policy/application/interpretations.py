from __future__ import annotations

import logging
import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.columns import ColumnSpec, overlong_reasons, string_lengths
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.domain.interpret_rules import KNOWN_INTERPRET_KEYS
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.policy.application import scenario_engine
from app.policy.application.importing import add_in_batches
from app.policy.application.policy_content import attach_policy_contents, policy_content
from app.policy.application.region import make_policy_uid, make_relation_key
from app.policy.domain.fields import (
    DATA_STATUS_CHOICES,
    DATA_STATUS_PENDING,
    INTERPRETATION_COLUMNS,
    INTERPRETATION_EXPORT_COLUMNS,
    POLICY_CONTENT_COLUMN,
    POLICY_TITLE_MAX,
    SCENARIO_CODE_FIELDS,
    SCENARIO_NAME_FIELDS,
)
from app.policy.domain.models import INTERPRETATION_WRITE_FIELDS, Interpretation
from app.policy.repositories import interpretations as repo
from app.policy.repositories import options as options_repo

INTERPRETATION_LENGTHS = {**string_lengths(Interpretation), "policy_title": POLICY_TITLE_MAX}

logger = logging.getLogger("policy.interpretations")


def to_out(row: Interpretation) -> dict[str, Any]:
    extra = dict(getattr(row, "ai_outputs", None) or {})
    data: dict[str, Any] = {
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
        "adapted_products": row.adapted_products,
        "purchase_reason": row.purchase_reason,
        "relation_key": row.relation_key,
        "opportunity_type": row.opportunity_type,
        "policy_summary": row.policy_summary,
        "has_subsidy": row.has_subsidy,
        "subsidy_content": row.subsidy_content,
        "market_opportunity": row.market_opportunity,
        "info_level": row.info_level,
        "is_new_scenario": row.is_new_scenario,
        "new_scenario_level": row.new_scenario_level,
        "remark": row.remark,
        "data_status": row.data_status,
        "scenario_state": row.scenario_state,
        "candidate_id": str(row.candidate_id) if row.candidate_id else "",
        "source_content_id": row.source_content_id or "",
        "tagged_at": format_beijing(row.tagged_at),
        "scenario_synced_at": format_beijing(row.scenario_synced_at),
        "ai_outputs": extra,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }
    for key, val in extra.items():
        if key not in data:
            data[key] = str(val or "")
    return data


def _values(data: dict[str, str]) -> dict[str, str]:
    values = {field: (data.get(field) or "").strip() for field in INTERPRETATION_WRITE_FIELDS}
    if not values["policy_uid"]:
        values["policy_uid"] = make_policy_uid(values["policy_title"])
    # 没填数据状态（新增、旧模板导入）一律按待验证入库，不留空值。
    if not values["data_status"]:
        values["data_status"] = DATA_STATUS_PENDING
    values["relation_key"] = make_relation_key(
        values["policy_uid"],
        values["industry_scenario_code"],
        values["opportunity_type"],
        [values[field] for field in SCENARIO_NAME_FIELDS],
    )
    return values


async def _refresh_codes(payload: dict[str, str], row: Interpretation | None) -> bool:
    """六级行业场景名称改了，或编码还空着，就按名称去码表查编码：查到填上，查不到清空，不留旧场景的编码。

    只在保存表单时查（新建、编辑），导入按文件里的编码。返回名称是否改过，改过的已同步行要清掉同步时间。
    """

    names = {field: (payload.get(field) or "").strip() for field in SCENARIO_NAME_FIELDS}
    renamed = row is not None and any(names[field] != (getattr(row, field) or "") for field in SCENARIO_NAME_FIELDS)
    codeless = not any((payload.get(field) or "").strip() for field in SCENARIO_CODE_FIELDS)
    if not (renamed or codeless):
        return False
    found: list[dict[str, Any]] = []
    if any(names.values()):
        try:
            found = await internal_clients.codebook(
                "POST", "/internal/v1/scenarios/lookup", json={"items": [{"key": "0", **names}]}
            )
        except DependencyUnavailableError as exc:
            if not renamed:
                return False  # 只是顺手补查，码表连不上不耽误保存，下次保存再补
            raise DependencyUnavailableError("改了行业场景名称要重查编码，码表服务暂时连不上，请稍后再保存") from exc
    codes = found[0] if found else {}
    for field in SCENARIO_CODE_FIELDS:
        payload[field] = str(codes.get(field) or "")
    return renamed


def _write_error(values: dict[str, str]) -> str | None:
    """新建、编辑、导入共用：数据状态取值和列宽。"""

    if message := _data_status_error(values):
        return message
    if reasons := overlong_reasons(values, INTERPRETATION_COLUMNS, INTERPRETATION_LENGTHS):
        return "、".join(reasons)
    return None


def _data_status_error(values: dict[str, str]) -> str | None:
    """数据状态只允许固定两项，写入前统一校验。"""

    if values["data_status"] in DATA_STATUS_CHOICES:
        return None
    return f"数据状态只能是{'、'.join(DATA_STATUS_CHOICES)}"


async def list_interpretations(session: AsyncSession, filters: Filters, *, page: int, page_size: int) -> dict[str, Any]:
    items, total = await repo.list_items(session, filters=filters, page=page, page_size=page_size)
    return {"items": [to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def _active_interpret_ai_fields() -> list[str]:
    fields: list[str] = []
    try:
        items = await internal_clients.ai("GET", "/internal/v1/online-templates", params={"category": "policy"})
        for item in items or []:
            item_fields = [str(f).strip() for f in (item.get("output_fields") or []) if str(f).strip()]
            if set(item_fields) & {"一级行业", "行业", "一级场景", "场景"}:
                fields.extend(name for name in item_fields if name not in KNOWN_INTERPRET_KEYS and name not in fields)
    except (ApiError, DependencyUnavailableError):
        logger.warning("AI 模板服务暂时取不到，解读表暂不附加动态模板字段")
    return fields


async def list_interpretation_options(session: AsyncSession) -> dict[str, Any]:
    data = await options_repo.interpretation_options(session)
    # 一级行业、一级场景的候选值是行业场景码表，不在几百万条解读上去重。码表服务暂时取不到时下拉为空。
    try:
        industries, scenarios = await internal_clients.scenario_l1_names()
    except DependencyUnavailableError:
        logger.warning("行业场景码表暂时取不到，筛选项先不给一级行业、一级场景")
        industries, scenarios = [], []
    data["options"]["industry_l1"] = {"items": industries, "truncated": False}
    data["options"]["scenario_l1_name"] = {"items": scenarios, "truncated": False}
    data["ai_fields"] = await _active_interpret_ai_fields()
    return data


async def search_interpretation_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(session, options_repo.INTERPRETATION_OPTION_COLUMNS, field=field, keyword=keyword)


async def get_interpretation(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    return to_out(row)


async def interpretation_content(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    return await policy_content(row.source_content_id)


def _apply_changes(row: Interpretation, values: dict[str, str], *, renamed: bool) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    # 同步过的新增场景改了名称，码表里那个场景已经不是它了：清掉同步时间，可以按新名称再同步一次。
    if renamed and row.scenario_synced_at is not None:
        changes["scenario_synced_at"] = {"from": format_beijing(row.scenario_synced_at), "to": ""}
        row.scenario_synced_at = None
    return changes


def _apply_ai_outputs(row: Interpretation, raw_outputs: Any) -> dict[str, Any]:
    if not isinstance(raw_outputs, dict):
        return {}
    current_extra = dict(getattr(row, "ai_outputs", None) or {})
    extra_changes: dict[str, Any] = {}
    for raw_k, raw_v in raw_outputs.items():
        key = str(raw_k).strip()
        if not key or key in INTERPRETATION_WRITE_FIELDS:
            continue
        new_val = str(raw_v or "").strip()
        old_val = str(current_extra.get(key) or "")
        if old_val != new_val:
            extra_changes[key] = {"from": old_val[:80], "to": new_val[:80]}
            current_extra[key] = new_val
    if extra_changes:
        row.ai_outputs = current_extra
    return extra_changes


async def update_interpretation(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    payload = {
        field: str((data[field] if field in data else getattr(row, field)) or "")
        for field in INTERPRETATION_WRITE_FIELDS
    }
    # 请求没带数据状态时沿用原值，避免旧客户端保存一次就把「人工验证」冲回「待验证」。
    if not payload["data_status"].strip():
        payload["data_status"] = row.data_status
    renamed = await _refresh_codes(payload, row)
    values = _values(payload)
    if not values["policy_title"]:
        raise ApiError("政策原文名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if message := _write_error(values):
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    existing = await repo.get_by_relation_key(session, values["relation_key"])
    if existing and existing.id != row.id:
        raise ApiError(
            "这条政策已有同一场景、同一机会类型的解读记录（关联主键重复），请改一下场景或机会类型",
            code=ErrorCode.DUPLICATE,
            http_status=409,
        )
    changes = {**_apply_changes(row, values, renamed=renamed), **_apply_ai_outputs(row, data.get("ai_outputs"))}
    if not changes:
        return to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    if renamed or any(field in changes for field in SCENARIO_CODE_FIELDS):
        # 场景换了：重新和码表比对、归集（可能落到已经决定过的候选，按决定处理）
        old_candidate = row.candidate_id
        row.scenario_state, row.candidate_id = "", None
        await scenario_engine.classify_quietly(session, [row], also=[old_candidate])
    await enqueue_event(
        session, event_type="policy.interpretation.updated", actor=actor, target_id=str(row.id), changes=changes
    )
    return to_out(row)


def _import_skip_reason(values: dict[str, str], seen: set[str]) -> str | None:
    if not values["policy_title"]:
        return "政策原文名称为空"
    if message := _write_error(values):
        return message
    if values["relation_key"] in seen:
        return "关联主键已存在"
    return None


def _build_rows(actor: Actor, accepted: list[dict[str, str]]) -> list[Interpretation]:
    now = utcnow()
    rows: list[Interpretation] = []
    for values in accepted:
        item_id = uuid.uuid4()
        rows.append(
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
    return rows


async def import_interpretations(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, INTERPRETATION_COLUMNS, subject="政策")
    skipped_rows: list[dict[str, str]] = []
    accepted: list[dict[str, str]] = []
    rows = [_values(item) for item in parsed]
    seen = await repo.existing_relation_keys(session, [values["relation_key"] for values in rows])
    for values in rows:
        reason = _import_skip_reason(values, seen)
        if reason:
            skipped_rows.append({**values, "skip_reason": reason})
            continue
        seen.add(values["relation_key"])
        accepted.append(values)
    built = _build_rows(actor, accepted)
    inserted = await add_in_batches(session, built)
    await scenario_engine.classify_quietly(session, built)
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
    items = await repo.list_filtered(session, filters)
    rows = [to_out(item) for item in items]
    await attach_policy_contents(session, items, rows)
    ai_fields: list[str] = []
    for row in rows:
        for key in row.get("ai_outputs") or ():
            if key not in INTERPRETATION_WRITE_FIELDS and key not in ai_fields:
                ai_fields.append(str(key))
    export_cols = (
        (*INTERPRETATION_COLUMNS, *(ColumnSpec(f, f) for f in ai_fields), POLICY_CONTENT_COLUMN)
        if ai_fields
        else INTERPRETATION_EXPORT_COLUMNS
    )
    await enqueue_event(session, event_type="policy.interpretation.exported", actor=actor, extra={"count": len(rows)})
    return await build_workbook_async(export_cols, rows, sheet_name="政策解读列表")
