"""报告库与方案库 Excel 导出、未定义数据导出与批量标签上传。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import build_workbook_async, encode_skipped_file_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.common.upload_utils import format_size
from app.core.config import get_settings
from app.library.application.library_write import normalize_library_values, validate_metadata_values
from app.library.domain.specs import LibrarySpec
from app.library.repositories import library as repo


def _export_row(spec: LibrarySpec, row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {field: getattr(row, field) for field in spec.business_fields}
    out["uploaded_at"] = format_beijing(row.uploaded_at)
    out["file_suffix"] = row.file_suffix
    out["file_size_display"] = format_size(row.file_size_bytes)
    return out


def _undefined_row(spec: LibrarySpec, row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"id": str(row.id)}
    for field in spec.business_fields:
        out[field] = getattr(row, field)
    out["file_suffix"] = row.file_suffix
    out["uploaded_at"] = format_beijing(row.uploaded_at)
    out["remark"] = row.remark
    return out


async def export_filtered_excel(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    filters: Filters,
) -> bytes:
    max_rows = get_settings().export_max_rows
    total = await repo.count_filtered(session, spec, filters, user_id=actor.id)
    if total > max_rows:
        raise ApiError(
            f"导出数据超过上限（{max_rows} 条），请先缩小筛选范围",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    rows = await repo.list_filtered(session, spec, filters, user_id=actor.id)
    payload = await build_workbook_async(
        spec.export_columns,
        [_export_row(spec, r) for r in rows],
        sheet_name=spec.sheet_name,
        include_audit=False,
    )
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.exported",
        actor=actor,
        changes={"row_count": len(rows), "filters": {k: v for k, v in filters.items() if v}},
    )
    return payload


async def export_undefined_excel(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
) -> bytes:
    max_rows = get_settings().export_max_rows
    total = await repo.count_undefined(session, spec)
    if total > max_rows:
        raise ApiError(
            f"导出未定义数据超过上限（{max_rows} 条），请分批维护",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    rows = await repo.list_undefined(session, spec)
    payload = await build_workbook_async(
        spec.undefined_columns,
        [_undefined_row(spec, r) for r in rows],
        sheet_name="未定义标签数据",
        include_audit=False,
    )
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.export_undefined",
        actor=actor,
        changes={"row_count": len(rows), "file_ids": [str(r.id) for r in rows[:50]]},
    )
    return payload


async def _find_target_file(session: AsyncSession, spec: LibrarySpec, raw_id: str, title: str) -> Any | None:
    if raw_id:
        try:
            return await repo.get_for_update(session, spec, uuid.UUID(raw_id))
        except ValueError:
            return None
    if title:
        row = await repo.get_by_title(session, spec, title)
        if row is not None:
            return await repo.get_for_update(session, spec, row.id)
    return None


async def _process_tag_row(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    row_dict: dict[str, str],
    actor: Actor,
    now: Any,
) -> tuple[str, str | None]:
    raw_id = row_dict.get("id", "").strip()
    title = row_dict.get(spec.title_field, "").strip()
    if not raw_id and not title:
        return "skipped", f"缺少文件ID和{spec.item_noun}名称"
    target = await _find_target_file(session, spec, raw_id, title)
    if target is None:
        return "skipped", spec.not_found_msg

    writable = {f: row_dict.get(f, "").strip() for f in spec.tag_writable_fields if f in row_dict}
    cleaned = normalize_library_values(spec, writable)
    reasons = validate_metadata_values(spec, cleaned)
    if reasons:
        return "skipped", "；".join(reasons)

    changed_fields: list[str] = []
    for field, new_val in cleaned.items():
        if str(getattr(target, field) or "") != new_val:
            setattr(target, field, new_val)
            changed_fields.append(field)
    target.is_defined = spec.is_defined_values(target)
    if not changed_fields:
        return "unchanged", None

    target.version += 1
    target.updated_at = now
    target.updated_by_id = actor.id
    target.updated_by_name = actor.name
    await repo.add_op_log(
        session,
        spec,
        file_id=target.id,
        actor=actor,
        op_type="上传标签",
        detail=f"批量上传标签更新：{', '.join(changed_fields)}",
    )
    return "updated", None


def _row_lock_sort_key(spec: LibrarySpec, row_dict: dict[str, str]) -> tuple[int, str]:
    raw_id = row_dict.get("id", "").strip()
    if raw_id:
        return (0, raw_id.lower())
    return (1, row_dict.get(spec.title_field, "").strip())


async def upload_tags(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    content: bytes,
) -> dict[str, Any]:
    rows = await parse_sheet_async(content, spec.undefined_columns, subject=spec.tag_subject)
    if not rows:
        raise ApiError("上传的标签表为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)

    now = utcnow()
    updated = 0
    skipped_rows: list[dict[str, Any]] = []
    updated_names: list[str] = []

    for row_dict in sorted(rows, key=lambda item: _row_lock_sort_key(spec, item)):
        status, reason = await _process_tag_row(session, spec, row_dict=row_dict, actor=actor, now=now)
        if status == "updated":
            updated += 1
            updated_names.append(row_dict.get(spec.title_field) or row_dict.get("id") or "")
        elif status == "skipped":
            skipped_rows.append({**row_dict, "skip_reason": reason or "校验失败"})

    skipped_file = (
        await encode_skipped_file_async(spec.undefined_columns, skipped_rows, sheet_name="跳过明细")
        if skipped_rows
        else None
    )
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.upload_tags",
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
