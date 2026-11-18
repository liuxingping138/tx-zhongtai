"""知识库写入用例：上传文件、编辑标签元数据、删除文件与枚举/长度校验。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, ErrorCode, PermissionDeniedError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core import storage
from app.core.config import get_settings
from app.knowledge.application.knowledge import audit_denial, format_size, require_file, to_out
from app.knowledge.domain.fields import UNDEFINED_TAG_COLUMNS
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import (
    FILE_TYPES,
    INDUSTRY_TYPES,
    MARKET_CATEGORIES,
    OPERATOR_TYPES,
    PRODUCT_TYPES,
    KnowledgeAccess,
    normalize_file_type_input,
    split_multi_tags,
)
from app.knowledge.repositories import knowledge as repo

EDITABLE_FIELDS = (
    "file_name",
    "file_type",
    "operator_type",
    "depart_affiliation",
    "industry_type",
    "app_scenario",
    "market_category",
    "product_type",
    "product_sub_type",
    "prov_name",
    "data_time",
    "remark",
)

FILE_LENGTHS = string_lengths(KnowledgeFile)


async def _assert_edit(
    session: AsyncSession,
    actor: Actor,
    access: KnowledgeAccess,
    row: KnowledgeFile,
    *,
    action: str,
    target_scope: tuple[str, str] | None = None,
) -> None:
    file_type, industry_type = target_scope if target_scope is not None else (row.file_type, row.industry_type)
    try:
        access.require_edit(file_type, industry_type)
    except PermissionDeniedError as exc:
        await audit_denial(session, actor=actor, row=row, action=action, reason=str(exc))
        raise


def validate_metadata_values(data: dict[str, str]) -> list[str]:
    """返回校验错误列表，供编辑接口和批量上传标签共用。"""

    reasons = overlong_reasons(data, UNDEFINED_TAG_COLUMNS, FILE_LENGTHS)
    if "file_type" in data:
        ft = normalize_file_type_input(data["file_type"])
        if ft and ft not in FILE_TYPES:
            reasons.append(f"不支持的文件类型：{ft}")
    if data.get("operator_type") and data["operator_type"] not in OPERATOR_TYPES:
        reasons.append(f"不支持的运营商类型：{data['operator_type']}")
    if data.get("market_category") and data["market_category"] not in MARKET_CATEGORIES:
        reasons.append(f"不支持的市场类别：{data['market_category']}")
    if data.get("industry_type"):
        bad = [part for part in split_multi_tags(data["industry_type"]) if part not in INDUSTRY_TYPES]
        if bad:
            reasons.append(f"不支持的行业类型：{'、'.join(bad)}")
    if data.get("product_type"):
        bad = [part for part in split_multi_tags(data["product_type"]) if part not in PRODUCT_TYPES]
        if bad:
            reasons.append(f"不支持的产品类型：{'、'.join(bad)}")
    return reasons


def _raise_if_invalid(data: dict[str, str]) -> None:
    reasons = validate_metadata_values(data)
    if reasons:
        raise ApiError("、".join(reasons), code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def update_metadata(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    file_id: uuid.UUID,
    data: dict[str, Any],
) -> dict[str, Any]:
    row = await require_file(session, file_id, lock=True)
    await _assert_edit(session, actor, access, row, action="update")
    if data.get("version") != row.version:
        raise VersionConflictError("该资料已被他人更新，请刷新后重试")
    cleaned = {k: str(v or "").strip() for k, v in data.items() if k in EDITABLE_FIELDS}
    if "file_type" in cleaned:
        cleaned["file_type"] = normalize_file_type_input(cleaned["file_type"])
    _raise_if_invalid(cleaned)
    if "file_name" in cleaned and not cleaned["file_name"]:
        raise ApiError("资料名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    next_ft = cleaned.get("file_type", row.file_type)
    next_ind = cleaned.get("industry_type", row.industry_type)
    await _assert_edit(session, actor, access, row, action="update_target_scope", target_scope=(next_ft, next_ind))

    changes: dict[str, Any] = {}
    for field, new_val in cleaned.items():
        old_val = str(getattr(row, field) or "")
        if old_val != new_val:
            changes[field] = {"from": old_val, "to": new_val}
            setattr(row, field, new_val)

    row.is_defined = bool(row.file_type)
    if changes:
        now = utcnow()
        row.version += 1
        row.updated_at = now
        row.updated_by_id = actor.id
        row.updated_by_name = actor.name
        await repo.add_op_log(
            session,
            file_id=row.id,
            actor_id=actor.id,
            actor_name=actor.name,
            op_type="编辑",
            detail=f"更新字段：{', '.join(changes.keys())}",
        )
        await enqueue_event(
            session,
            event_type="thinktank.knowledge.updated",
            actor=actor,
            target_id=str(row.id),
            changes={"file_name": row.file_name, **changes},
        )
    fav = await repo.is_favorited(session, user_id=actor.id, file_id=row.id)
    return to_out(row, is_favorited=fav, access=access)


async def upload_knowledge_file(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    filename: str,
    content: bytes,
    metadata: dict[str, str],
) -> dict[str, Any]:
    clean_name = filename.strip()
    if not clean_name:
        raise ApiError("请提供有效的文件名", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    ext = storage.raw_extension(clean_name)
    if ext not in storage.ALLOWED_SUFFIXES:
        raise ApiError(
            "仅支持 PDF、Excel、Word、PPT、TXT、CSV、MD 文件",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    cleaned = {k: str(v or "").strip() for k, v in metadata.items() if k in EDITABLE_FIELDS}
    cleaned["file_type"] = normalize_file_type_input(cleaned.get("file_type"))
    _raise_if_invalid({**cleaned, "file_name": clean_name})
    file_type = cleaned["file_type"]
    industry_type = cleaned.get("industry_type", "")
    try:
        access.require_edit(file_type, industry_type)
    except PermissionDeniedError as exc:
        await enqueue_event(
            session,
            event_type="thinktank.knowledge.access_denied",
            actor=actor,
            target_id=clean_name,
            changes={
                "file_name": clean_name,
                "file_type": file_type or "未定义",
                "industry_type": industry_type or "无",
                "attempted_action": "upload",
                "reason": str(exc),
            },
            extra={"outcome": "denied"},
        )
        await session.commit()
        raise

    now = utcnow()
    file_id = uuid.uuid4()
    rel_path = storage.new_object_key(file_id, ext.lower())
    await storage.save_object(
        get_settings(),
        rel_path,
        content,
        content_type=storage.media_type_for_file(clean_name, ext),
    )

    row = KnowledgeFile(
        id=file_id,
        file_name=clean_name,
        file_type=file_type,
        operator_type=cleaned.get("operator_type", ""),
        depart_affiliation=cleaned.get("depart_affiliation", ""),
        industry_type=industry_type,
        app_scenario=cleaned.get("app_scenario", ""),
        market_category=cleaned.get("market_category", ""),
        product_type=cleaned.get("product_type", ""),
        product_sub_type=cleaned.get("product_sub_type", ""),
        prov_name=cleaned.get("prov_name", ""),
        data_time=cleaned.get("data_time", ""),
        uploaded_at=now,
        file_suffix=storage.normalize_suffix(clean_name),
        file_size_bytes=len(content),
        storage_path=rel_path,
        content_text="",
        remark=cleaned.get("remark", ""),
        is_defined=bool(file_type),
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
    await repo.add_op_log(
        session,
        file_id=row.id,
        actor_id=actor.id,
        actor_name=actor.name,
        op_type="上传",
        detail=f"上传资料「{row.file_name}」（{format_size(len(content))}）",
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.created",
        actor=actor,
        target_id=str(row.id),
        changes={
            "file_name": row.file_name,
            "file_type": row.file_type or "未定义",
            "industry_type": row.industry_type or "无",
            "file_size_bytes": len(content),
        },
    )
    return to_out(row, is_favorited=False, access=access)


async def delete_knowledge_file(
    session: AsyncSession, *, actor: Actor, access: KnowledgeAccess, file_id: uuid.UUID
) -> dict[str, bool]:
    row = await require_file(session, file_id, lock=True)
    await _assert_edit(session, actor, access, row, action="delete")
    rel_path = row.storage_path
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.deleted",
        actor=actor,
        target_id=str(row.id),
        changes={
            "file_name": row.file_name,
            "file_type": row.file_type or "未定义",
            "industry_type": row.industry_type or "无",
        },
    )
    await session.delete(row)
    await session.flush()
    if storage.is_managed_object_key(rel_path, row.id):
        await storage.delete_object(get_settings(), rel_path)
    return {"deleted": True}
