"""报告库与方案库写入用例：上传、编辑（乐观锁）、删除与元数据清洗校验。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.columns import overlong_reasons
from platform_common.errors import ApiError, ErrorCode, VersionConflictError
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import preview as common_preview
from app.common.audit_emit import enqueue_event
from app.common.security import LibraryAccess
from app.common.upload_utils import format_size, normalize_pipe_value, sanitize_filename, sanitize_title
from app.core import storage
from app.core.config import get_settings
from app.library.application.library_read import preview_subject, require_file, to_out
from app.library.domain.specs import LibrarySpec
from app.library.repositories import library as repo

logger = get_logger(__name__)


def normalize_library_values(spec: LibrarySpec, data: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for field in spec.editable_fields:
        if field not in data:
            continue
        val = str(data[field] or "").strip()
        if field in spec.pipe_fields:
            val = normalize_pipe_value(val)
        cleaned[field] = val
    return cleaned


def validate_metadata_values(spec: LibrarySpec, data: dict[str, str]) -> list[str]:
    reasons = overlong_reasons(data, spec.undefined_columns, spec.field_lengths())
    if "is_temp_support" in data and data["is_temp_support"] and data["is_temp_support"] not in {"是", "否"}:
        reasons.append(f"不支持的是否临时支撑取值：{data['is_temp_support']}")
    return reasons


def _raise_if_invalid(spec: LibrarySpec, data: dict[str, str]) -> None:
    reasons = validate_metadata_values(spec, data)
    if reasons:
        raise ApiError("、".join(reasons), code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def update_metadata(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    access: LibraryAccess,
    file_id: uuid.UUID,
    data: dict[str, Any],
) -> dict[str, Any]:
    row = await require_file(session, spec, file_id, lock=True)
    if data.get("version") != row.version:
        raise VersionConflictError(f"该{spec.item_noun}已被他人更新，请刷新后重试")

    cleaned = normalize_library_values(spec, data)
    if spec.title_field in cleaned:
        cleaned[spec.title_field] = sanitize_title(cleaned[spec.title_field])
        if not cleaned[spec.title_field]:
            raise ApiError(f"{spec.item_noun}名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    _raise_if_invalid(spec, cleaned)

    changes: dict[str, Any] = {}
    for field, new_val in cleaned.items():
        old_val = str(getattr(row, field) or "")
        if old_val != new_val:
            changes[field] = {"from": old_val, "to": new_val}
            setattr(row, field, new_val)

    row.is_defined = spec.is_defined_values(row)
    if changes:
        now = utcnow()
        row.version += 1
        row.updated_at = now
        row.updated_by_id = actor.id
        row.updated_by_name = actor.name
        await repo.add_op_log(
            session,
            spec,
            file_id=row.id,
            actor=actor,
            op_type="编辑",
            detail=f"更新字段：{', '.join(changes.keys())}",
        )
        await enqueue_event(
            session,
            event_type=f"{spec.event_prefix}.updated",
            actor=actor,
            target_id=str(row.id),
            changes={spec.title_field: str(getattr(row, spec.title_field) or ""), **changes},
        )
    fav = await repo.is_favorited(session, spec, user_id=actor.id, file_id=row.id)
    return to_out(spec, row, is_favorited=fav, access=access)


@dataclass(frozen=True)
class UploadPayload:
    filename: str
    content: bytes
    metadata: dict[str, str]


async def upload_file(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    access: LibraryAccess,
    payload: UploadPayload,
) -> dict[str, Any]:
    clean_name = sanitize_filename(payload.filename)
    if not clean_name:
        raise ApiError("请提供有效的文件名", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    ext = storage.raw_extension(clean_name)
    if ext not in storage.ALLOWED_SUFFIXES:
        raise ApiError(
            "仅支持 PDF、Excel、Word、PPT、TXT、CSV、MD 文件",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )

    cleaned = normalize_library_values(spec, payload.metadata)
    content = payload.content
    raw_title = cleaned.get(spec.title_field, "")
    title = sanitize_title(raw_title) if raw_title else clean_name
    cleaned[spec.title_field] = title
    _raise_if_invalid(spec, cleaned)

    now = utcnow()
    file_id = uuid.uuid4()
    rel_path = storage.new_object_key(file_id, ext.lower(), prefix=spec.storage_prefix)
    settings = get_settings()
    try:
        await storage.save_object(
            settings,
            rel_path,
            content,
            content_type=storage.media_type_for_file(clean_name, ext),
        )
    except storage.StorageUnavailableError as exc:
        raise ApiError(
            "文件存储服务暂不可用，上传失败，请稍后重试",
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            http_status=503,
        ) from exc

    row_kwargs: dict[str, Any] = {field: cleaned.get(field, "") for field in spec.business_fields}
    row = spec.file_model(
        id=file_id,
        **row_kwargs,
        uploaded_at=now,
        file_suffix=storage.normalize_suffix(clean_name),
        file_size_bytes=len(content),
        storage_path=rel_path,
        content_text="",
        remark=cleaned.get("remark", ""),
        is_defined=False,
        version=1,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
    )
    row.is_defined = spec.is_defined_values(row)
    try:
        session.add(row)
        await session.flush()
        await repo.add_op_log(
            session,
            spec,
            file_id=row.id,
            actor=actor,
            op_type="上传",
            detail=f"上传{spec.item_noun}「{title}」（{format_size(len(content))}）",
        )
        await enqueue_event(
            session,
            event_type=f"{spec.event_prefix}.created",
            actor=actor,
            target_id=str(row.id),
            changes={
                spec.title_field: title,
                spec.category_field: str(getattr(row, spec.category_field) or ""),
                "file_size_bytes": len(content),
            },
        )
        await session.commit()
    except Exception:
        try:
            await storage.delete_object(settings, rel_path)
        except Exception as cleanup_exc:  # noqa: BLE001  写库失败后的尽力补偿清理，不掩盖原始异常
            logger.warning("library_upload_orphan_cleanup_failed", path=rel_path, error=str(cleanup_exc))
        raise
    return to_out(spec, row, is_favorited=False, access=access)


async def delete_file(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    file_id: uuid.UUID,
) -> dict[str, bool]:
    row = await require_file(session, spec, file_id, lock=True)
    title = str(getattr(row, spec.title_field) or "")
    rel_path = str(row.storage_path or "")
    subject = preview_subject(spec, row)
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.deleted",
        actor=actor,
        target_id=str(row.id),
        changes={spec.title_field: title, spec.category_field: str(getattr(row, spec.category_field) or "")},
    )
    await session.delete(row)
    await session.flush()
    await session.commit()
    await common_preview.drop_preview_cache(get_settings(), subject)
    if storage.is_managed_object_key(rel_path, row.id, prefix=spec.storage_prefix):
        try:
            await storage.delete_object(get_settings(), rel_path)
        except storage.StorageUnavailableError as exc:
            logger.warning("library_delete_object_failed", file_id=str(row.id), path=rel_path, error=str(exc))
    return {"deleted": True}
