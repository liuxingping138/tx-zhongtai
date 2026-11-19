"""知识库只读与互动用例：列表查询、详情、预览、下载、收藏、单文件操作日志及范围鉴权审计。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing
from platform_common.errors import ApiError, ErrorCode, NotFoundError, PermissionDeniedError
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.common.codebook_client import get_provinces
from app.core import storage
from app.core.config import get_settings
from app.knowledge.domain.models import KnowledgeFile, KnowledgeOpLog
from app.knowledge.domain.scopes import PROVINCES, KnowledgeAccess
from app.knowledge.repositories import knowledge as repo


@dataclass(frozen=True)
class FileContentResult:
    content: bytes
    filename: str
    media_type: str


@dataclass(frozen=True)
class FileStreamResult:
    stream: AsyncIterator[bytes]
    filename: str
    media_type: str
    content_length: int | None = None


def format_size(size_bytes: int) -> str:
    return f"{size_bytes / 1024:.2f} kb"


def to_out(row: KnowledgeFile, *, is_favorited: bool, access: KnowledgeAccess) -> dict[str, Any]:
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
        "uploaded_at": format_beijing(row.uploaded_at),
        "file_suffix": row.file_suffix,
        "file_size_bytes": row.file_size_bytes,
        "file_size_display": format_size(row.file_size_bytes),
        "remark": row.remark,
        "is_defined": row.is_defined,
        "is_favorited": is_favorited,
        "can_export": access.can_export_record(row.file_type, row.industry_type),
        "can_edit": access.can_edit_record(row.file_type, row.industry_type),
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


def _log_out(row: KnowledgeOpLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "file_id": str(row.file_id),
        "actor_id": row.actor_id,
        "actor_name": row.actor_name,
        "op_type": row.op_type,
        "detail": row.detail,
        "created_at": format_beijing(row.created_at),
    }


async def require_file(session: AsyncSession, file_id: uuid.UUID, *, lock: bool = False) -> KnowledgeFile:
    row = await (repo.get_for_update(session, file_id) if lock else repo.get_by_id(session, file_id))
    if row is None:
        raise NotFoundError("知识文件不存在")
    return row


async def audit_denial(
    session: AsyncSession,
    *,
    actor: Actor,
    row: KnowledgeFile,
    action: str,
    reason: str,
) -> None:
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.access_denied",
        actor=actor,
        target_id=str(row.id),
        changes={
            "file_name": row.file_name,
            "file_type": row.file_type or "未定义",
            "industry_type": row.industry_type or "无",
            "attempted_action": action,
            "reason": reason,
        },
        extra={"outcome": "denied"},
    )
    # 拒绝时外层抛 403 会触发 get_db_session 回滚；提交当前事务留住越权审计。
    await session.commit()


async def assert_read(
    session: AsyncSession, actor: Actor, access: KnowledgeAccess, row: KnowledgeFile, action: str
) -> None:
    try:
        access.require_read(row.file_type, row.industry_type)
    except PermissionDeniedError as exc:
        await audit_denial(session, actor=actor, row=row, action=action, reason=str(exc))
        raise


async def assert_export(
    session: AsyncSession, actor: Actor, access: KnowledgeAccess, row: KnowledgeFile, action: str
) -> None:
    try:
        access.require_export(row.file_type, row.industry_type)
    except PermissionDeniedError as exc:
        await audit_denial(session, actor=actor, row=row, action=action, reason=str(exc))
        raise


async def list_knowledge(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    filters: Filters,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    rows, total = await repo.list_items(
        session,
        filters=filters,
        access=access,
        user_id=actor.id,
        page=page,
        page_size=page_size,
    )
    fav_ids = await repo.favorite_ids_for_user(session, user_id=actor.id, file_ids=[r.id for r in rows])
    return {
        "items": [to_out(row, is_favorited=row.id in fav_ids, access=access) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_options(session: AsyncSession, *, access: KnowledgeAccess) -> dict[str, Any]:
    provinces = await get_provinces(get_settings(), PROVINCES)
    return await repo.list_options(session, access=access, provinces=provinces)


async def search_options(
    session: AsyncSession,
    *,
    field: str,
    keyword: str | None,
    access: KnowledgeAccess | None = None,
) -> list[str]:
    provinces = await get_provinces(get_settings(), PROVINCES) if field == "prov_name" else None
    return await repo.search_option_values(session, field=field, keyword=keyword, provinces=provinces, access=access)


async def get_detail(
    session: AsyncSession, *, actor: Actor, access: KnowledgeAccess, file_id: uuid.UUID
) -> dict[str, Any]:
    row = await require_file(session, file_id)
    await assert_read(session, actor, access, row, "read")
    fav = await repo.is_favorited(session, user_id=actor.id, file_id=row.id)
    return to_out(row, is_favorited=fav, access=access)


async def preview_knowledge(
    session: AsyncSession, *, actor: Actor, access: KnowledgeAccess, file_id: uuid.UUID
) -> dict[str, Any]:
    row = await require_file(session, file_id)
    await assert_read(session, actor, access, row, "preview")
    fav = await repo.is_favorited(session, user_id=actor.id, file_id=row.id)
    await repo.add_op_log(
        session,
        file_id=row.id,
        actor_id=actor.id,
        actor_name=actor.name,
        op_type="预览",
        detail=f"预览资料「{row.file_name}」",
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.previewed",
        actor=actor,
        target_id=str(row.id),
        changes={
            "file_name": row.file_name,
            "file_type": row.file_type or "未定义",
            "industry_type": row.industry_type or "无",
        },
    )
    ext = storage.raw_extension(row.file_name) or row.file_suffix.upper()
    if row.storage_path and ext == "PDF":
        mode = "pdf"
    elif row.storage_path and ext in {"TXT", "MD", "CSV"}:
        mode = "text"
    else:
        mode = "summary"
    fallback_text = (
        f"资料名称：{row.file_name}\n文件类型：{row.file_type or '未定义'}\n行业类型：{row.industry_type or '无'}"
    )
    return {
        "item": to_out(row, is_favorited=fav, access=access),
        "preview": {
            "mode": mode,
            "has_binary": bool(row.storage_path),
            "content_text": row.content_text or fallback_text,
        },
    }


def _fallback_summary_bytes(row: KnowledgeFile) -> bytes:
    lines = [
        f"资料名称：{row.file_name}",
        f"文件类型：{row.file_type or '未定义'}",
        f"运营商类型：{row.operator_type or '-'}",
        f"部门归属：{row.depart_affiliation or '-'}",
        f"行业类型：{row.industry_type or '无'}",
        f"应用场景：{row.app_scenario or '无'}",
        f"市场类别：{row.market_category or '无'}",
        f"产品类型：{row.product_type or '无'}",
        f"产品子类型：{row.product_sub_type or '无'}",
        f"省份：{row.prov_name or '-'}",
        f"资料时间：{row.data_time or '-'}",
        "",
        row.content_text or "（示例知识资料摘要）",
    ]
    return "\n".join(lines).encode("utf-8")


async def _record_download_audit(session: AsyncSession, actor: Actor, row: KnowledgeFile) -> None:
    await repo.add_op_log(
        session,
        file_id=row.id,
        actor_id=actor.id,
        actor_name=actor.name,
        op_type="下载",
        detail=f"下载资料「{row.file_name}」",
    )
    await enqueue_event(
        session,
        event_type="thinktank.knowledge.downloaded",
        actor=actor,
        target_id=str(row.id),
        changes={
            "file_name": row.file_name,
            "file_type": row.file_type or "未定义",
            "industry_type": row.industry_type or "无",
        },
    )


async def read_file_content(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    file_id: uuid.UUID,
    for_download: bool,
) -> FileContentResult:
    res = await stream_file_content(session, actor=actor, access=access, file_id=file_id, for_download=for_download)
    content = b"".join([chunk async for chunk in res.stream])
    return FileContentResult(content=content, filename=res.filename, media_type=res.media_type)


async def _single_chunk_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def stream_file_content(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    file_id: uuid.UUID,
    for_download: bool,
) -> FileStreamResult:
    row = await require_file(session, file_id)
    if for_download:
        await assert_export(session, actor, access, row, "download")
    else:
        await assert_read(session, actor, access, row, "preview_content")

    settings = get_settings()
    try:
        opened = await storage.stream_object(settings, row.storage_path)
    except storage.StorageUnavailableError as exc:
        raise ApiError(
            "文件存储服务暂不可用，请稍后重试",
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            http_status=503,
        ) from exc

    if opened is not None:
        stream, size = opened
        media_type = storage.media_type_for_file(row.file_name, row.file_suffix)
        filename = row.file_name
    else:
        raw = _fallback_summary_bytes(row)
        stream, size = _single_chunk_stream(raw), len(raw)
        media_type = "text/plain; charset=utf-8"
        filename = f"{row.file_name}.txt"

    if for_download:
        await _record_download_audit(session, actor, row)
    return FileStreamResult(stream=stream, filename=filename, media_type=media_type, content_length=size)


async def toggle_favorite(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    file_id: uuid.UUID,
    favorite: bool,
) -> dict[str, Any]:
    row = await require_file(session, file_id)
    await assert_read(session, actor, access, row, "favorite" if favorite else "unfavorite")
    changed = await repo.set_favorite(session, user_id=actor.id, file_id=row.id, favorite=favorite)
    if changed:
        op_label = "收藏" if favorite else "取消收藏"
        event_type = "thinktank.knowledge.favorited" if favorite else "thinktank.knowledge.unfavorited"
        await repo.add_op_log(
            session,
            file_id=row.id,
            actor_id=actor.id,
            actor_name=actor.name,
            op_type=op_label,
            detail=f"{op_label}资料「{row.file_name}」",
        )
        await enqueue_event(
            session,
            event_type=event_type,
            actor=actor,
            target_id=str(row.id),
            changes={
                "file_name": row.file_name,
                "file_type": row.file_type or "未定义",
                "industry_type": row.industry_type or "无",
                "is_favorited": favorite,
            },
        )
    return {"id": str(row.id), "is_favorited": favorite}


async def list_logs(
    session: AsyncSession,
    *,
    actor: Actor,
    access: KnowledgeAccess,
    file_id: uuid.UUID,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    row = await require_file(session, file_id)
    await assert_read(session, actor, access, row, "logs")
    items, total = await repo.list_op_logs(session, file_id=row.id, page=page, page_size=page_size)
    return {"items": [_log_out(item) for item in items], "total": total, "page": page, "page_size": page_size}
