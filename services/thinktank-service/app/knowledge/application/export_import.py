"""知识库 Excel 导出（筛选列表 / 导出未定义数据）与批量上传知识标签。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, PermissionDeniedError
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.knowledge.application.knowledge import format_size
from app.knowledge.application.knowledge_write import validate_metadata_values
from app.knowledge.domain.fields import KNOWLEDGE_EXPORT_COLUMNS, TAG_WRITABLE_FIELDS, UNDEFINED_TAG_COLUMNS
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import KnowledgeAccess, normalize_file_type_input
from app.knowledge.repositories import knowledge as repo


def _export_row(row: KnowledgeFile) -> dict[str, Any]:
    return {
        "file_name": row.file_name,
        "file_type": row.file_type or "未定义",
        "operator_type": row.operator_type,
        "depart_affiliation": row.depart_affiliation,
        "industry_type": row.industry_type,
        "app_scenario": row.app_scenario,
        "market_category": row.market_category,
        "product_type": row.product_type,
        "product_sub_type": row.product_sub_type,
        "prov_name": row.prov_name,
        "data_time": row.data_time,
        "uploaded_at": format_beijing(row.uploaded_at),
        "file_suffix": row.file_suffix,
        "file_size_display": format_size(row.file_size_bytes),
    }


def _undefined_row(row: KnowledgeFile) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "file_name": row.file_name,
        "file_type": row.file_type,
        "operator_type": row.operator_type,
        "depart_affiliation": row.depart_affiliation,
        "industry_type": row.industry_type,
        "app_scenario": row.app_scenario,
        "market_category": row.market_category,
        "product_type": row.product_type,
        "product_sub_type": row.product_sub_type,
        "prov_name": row.prov_name,
        "data_time": row.data_time,
        "file_suffix": row.file_suffix,
        "uploaded_at": format_beijing(row.uploaded_at),
        "remark": row.remark,
    }


async def export_filtered_excel(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    filters: Filters,
) -> bytes:
    max_rows = get_settings().export_max_rows
    total = await repo.count_filtered(session, filters, access=access, user_id=actor.id)
    if total > max_rows:
        raise ApiError(
            f"导出数据超过上限（{max_rows} 条），请先缩小筛选范围",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    rows = await repo.list_filtered(session, filters, access=access, user_id=actor.id)
    payload = await build_workbook_async(
        KNOWLEDGE_EXPORT_COLUMNS,
        [_export_row(r) for r in rows],
        sheet_name="知识库资料",
        include_audit=False,
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.exported",
        actor=actor,
        changes={"row_count": len(rows), "filters": {k: v for k, v in filters.items() if v}},
    )
    return payload


async def export_undefined_excel(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
) -> bytes:
    if "" not in access.exportable_file_types:
        await enqueue_event(
            session,
            event_type="thinktank.knowledge.access_denied",
            actor=actor,
            target_id="undefined",
            changes={
                "file_type": "未定义",
                "attempted_action": "export_undefined",
                "reason": "没有「未定义文件」范围的导出权限",
            },
            extra={"outcome": "denied"},
        )
        await session.commit()
        raise PermissionDeniedError("没有「未定义文件」范围的导出权限")
    max_rows = get_settings().export_max_rows
    total = await repo.count_undefined(session, access=access)
    if total > max_rows:
        raise ApiError(
            f"导出未定义数据超过上限（{max_rows} 条），请分批维护",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    rows = await repo.list_undefined(session, access=access)
    payload = await build_workbook_async(
        UNDEFINED_TAG_COLUMNS,
        [_undefined_row(r) for r in rows],
        sheet_name="未定义标签数据",
        include_audit=False,
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.export_undefined",
        actor=actor,
        changes={
            "row_count": len(rows),
            "file_ids": [str(r.id) for r in rows[:50]],
        },
    )
    return payload


async def _find_target_file(session: AsyncSession, raw_id: str, file_name: str) -> KnowledgeFile | None:
    if raw_id:
        try:
            return await repo.get_for_update(session, uuid.UUID(raw_id))
        except ValueError:
            return None
    if file_name:
        row = await repo.get_by_file_name(session, file_name)
        if row is not None:
            return await repo.get_for_update(session, row.id)
    return None


def _check_tag_row_permission(
    access: KnowledgeAccess, target: KnowledgeFile, next_ft: str, next_ind: str
) -> str | None:
    if not access.can_edit_record(target.file_type, target.industry_type):
        return f"没有原范围「{target.file_type or '未定义'} / {target.industry_type or '无'}」的管理编辑权限"
    if not access.can_edit_record(next_ft, next_ind):
        return f"没有目标范围「{next_ft or '未定义'} / {next_ind or '无'}」的管理编辑权限"
    return None


async def _process_tag_row(
    session: AsyncSession,
    *,
    row_dict: dict[str, str],
    actor: Actor,
    access: KnowledgeAccess,
    now: Any,
) -> tuple[str, str | None]:
    raw_id = row_dict.get("id", "").strip()
    file_name = row_dict.get("file_name", "").strip()
    if not raw_id and not file_name:
        return "skipped", "缺少文件ID和资料名称"
    target = await _find_target_file(session, raw_id, file_name)
    if target is None:
        return "skipped", "未找到对应的知识文件"

    cleaned = {f: row_dict.get(f, "").strip() for f in TAG_WRITABLE_FIELDS if f in row_dict}
    if "file_type" in cleaned:
        cleaned["file_type"] = normalize_file_type_input(cleaned["file_type"])
    reasons = validate_metadata_values(cleaned)
    if reasons:
        return "skipped", "；".join(reasons)

    next_ft = cleaned.get("file_type", target.file_type)
    next_ind = cleaned.get("industry_type", target.industry_type)
    if denied_reason := _check_tag_row_permission(access, target, next_ft, next_ind):
        return "skipped", denied_reason

    changed_fields: list[str] = []
    for field, new_val in cleaned.items():
        if str(getattr(target, field) or "") != new_val:
            setattr(target, field, new_val)
            changed_fields.append(field)
    target.is_defined = bool(target.file_type)
    if not changed_fields:
        return "unchanged", None

    target.version += 1
    target.updated_at = now
    target.updated_by_id = actor.id
    target.updated_by_name = actor.name
    await repo.add_op_log(
        session,
        file_id=target.id,
        actor_id=actor.id,
        actor_name=actor.name,
        op_type="上传标签",
        detail=f"批量上传标签更新：{', '.join(changed_fields)}",
    )
    return "updated", None


def _row_lock_sort_key(row_dict: dict[str, str]) -> tuple[int, str]:
    raw_id = row_dict.get("id", "").strip()
    if raw_id:
        return (0, raw_id.lower())
    return (1, row_dict.get("file_name", "").strip())


async def upload_knowledge_tags(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    content: bytes,
) -> dict[str, Any]:
    rows = await parse_sheet_async(content, UNDEFINED_TAG_COLUMNS, subject="知识标签")
    if not rows:
        raise ApiError("上传的标签表为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)

    now = utcnow()
    updated = 0
    skipped_rows: list[dict[str, Any]] = []
    updated_names: list[str] = []

    # 按稳定主键顺序加行锁，降低并发批量上传标签时交叉锁顺序导致的死锁风险。
    for row_dict in sorted(rows, key=_row_lock_sort_key):
        status, reason = await _process_tag_row(session, row_dict=row_dict, actor=actor, access=access, now=now)
        if status == "updated":
            updated += 1
            updated_names.append(row_dict.get("file_name") or row_dict.get("id") or "")
        elif status == "skipped":
            skipped_rows.append({**row_dict, "skip_reason": reason or "校验失败"})

    skipped_file = (
        await encode_skipped_file_async(UNDEFINED_TAG_COLUMNS, skipped_rows, sheet_name="跳过明细")
        if skipped_rows
        else None
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.upload_tags",
        actor=actor,
        changes={
            "total": len(rows),
            "updated": updated,
            "skipped": len(skipped_rows),
            "updated_files": updated_names[:50],
        },
    )
    return {
        "total": len(rows),
        "inserted": 0,
        "updated": updated,
        "skipped": len(skipped_rows),
        "rejected": False,
        "skipped_file": skipped_file,
    }
