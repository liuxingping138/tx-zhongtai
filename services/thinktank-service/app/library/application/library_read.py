"""报告库与方案库只读、预览、流式下载、收藏、日志与后台预热用例。"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks
from platform_common.actors import Actor
from platform_common.clock import format_beijing
from platform_common.errors import NotFoundError
from platform_common.filters import Filters
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import preview as common_preview
from app.common.audit_emit import enqueue_event
from app.common.codebook_client import get_thinktank_dicts
from app.common.preview import FileStreamResult, PreviewSubject
from app.common.security import LibraryAccess
from app.common.upload_utils import format_size
from app.core import office_preview, preview_slots, storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.library.domain.specs import LIBRARY_SPECS, LibrarySpec
from app.library.repositories import library as repo

logger = get_logger(__name__)
SessionFactory = Callable[[], AsyncSession]


def preview_subject(spec: LibrarySpec, row: Any) -> PreviewSubject:
    return PreviewSubject(
        file_id=str(row.id),
        filename=str(getattr(row, spec.title_field) or ""),
        file_suffix=str(row.file_suffix or ""),
        storage_path=str(row.storage_path or ""),
        file_size_bytes=int(row.file_size_bytes or 0),
    )


def fallback_summary_text(spec: LibrarySpec, row: Any) -> str:
    lines = [f"{label}：{getattr(row, field, '') or '-'}" for field, label in spec.summary_fields]
    if row.content_text:
        lines.extend(["", str(row.content_text)])
    return "\n".join(lines)


def to_out(spec: LibrarySpec, row: Any, *, is_favorited: bool, access: LibraryAccess) -> dict[str, Any]:
    out: dict[str, Any] = {"id": str(row.id)}
    for field in spec.business_fields:
        out[field] = getattr(row, field)
    out.update(
        {
            "uploaded_at": format_beijing(row.uploaded_at),
            "file_suffix": row.file_suffix,
            "file_size_bytes": row.file_size_bytes,
            "file_size_display": format_size(row.file_size_bytes),
            "remark": row.remark,
            "is_defined": row.is_defined,
            "is_favorited": is_favorited,
            "can_download": access.can_download,
            "can_export": access.can_export,
            "can_edit": access.can_edit,
            "version": row.version,
            "created_at": format_beijing(row.created_at),
            "created_by_name": row.created_by_name,
            "updated_at": format_beijing(row.updated_at),
            "updated_by_name": row.updated_by_name,
        }
    )
    return out


def _log_out(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "file_id": str(row.file_id),
        "actor_id": row.actor_id,
        "actor_name": row.actor_name,
        "op_type": row.op_type,
        "detail": row.detail,
        "created_at": format_beijing(row.created_at),
    }


async def require_file(
    session: AsyncSession,
    spec: LibrarySpec,
    file_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Any:
    row = await (repo.get_for_update(session, spec, file_id) if lock else repo.get_by_id(session, spec, file_id))
    if row is None:
        raise NotFoundError(spec.not_found_msg)
    return row


async def list_library(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    access: LibraryAccess,
    filters: Filters,
    pagination: tuple[int, int] = (1, 20),
) -> dict[str, Any]:
    page, page_size = pagination
    rows, total = await repo.list_items(
        session, spec, filters=filters, user_id=actor.id, page=page, page_size=page_size
    )
    fav_ids = await repo.favorite_ids_for_user(session, spec, user_id=actor.id, file_ids=[r.id for r in rows])
    return {
        "items": [to_out(spec, row, is_favorited=row.id in fav_ids, access=access) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_options(session: AsyncSession, spec: LibrarySpec) -> dict[str, Any]:
    dicts = await get_thinktank_dicts(get_settings())
    return await repo.list_options(session, spec, dicts=dicts)


async def search_options(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    field: str,
    keyword: str | None,
) -> list[str]:
    dicts = await get_thinktank_dicts(get_settings())
    return await repo.search_option_values(session, spec, field=field, keyword=keyword, dicts=dicts)


async def get_detail(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    access: LibraryAccess,
    file_id: uuid.UUID,
) -> dict[str, Any]:
    row = await require_file(session, spec, file_id)
    fav = await repo.is_favorited(session, spec, user_id=actor.id, file_id=row.id)
    return to_out(spec, row, is_favorited=fav, access=access)


async def preview_item(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    access: LibraryAccess,
    file_id: uuid.UUID,
) -> dict[str, Any]:
    row = await require_file(session, spec, file_id)
    title = str(getattr(row, spec.title_field) or "")
    fav = await repo.is_favorited(session, spec, user_id=actor.id, file_id=row.id)
    await repo.add_op_log(
        session,
        spec,
        file_id=row.id,
        actor=actor,
        op_type="预览",
        detail=f"预览{spec.item_noun}「{title}」",
    )
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.previewed",
        actor=actor,
        target_id=str(row.id),
        changes={spec.title_field: title, spec.category_field: str(getattr(row, spec.category_field) or "")},
    )
    subject = preview_subject(spec, row)
    mode = common_preview.preview_mode_for(subject)
    return {
        "item": to_out(spec, row, is_favorited=fav, access=access),
        "preview": {
            "mode": mode,
            "has_binary": bool(row.storage_path),
            "content_text": row.content_text or fallback_summary_text(spec, row),
        },
    }


async def _record_download_audit(session: AsyncSession, spec: LibrarySpec, actor: Actor, row: Any) -> None:
    title = str(getattr(row, spec.title_field) or "")
    await repo.add_op_log(
        session,
        spec,
        file_id=row.id,
        actor=actor,
        op_type="下载",
        detail=f"下载{spec.item_noun}「{title}」",
    )
    await enqueue_event(
        session,
        event_type=f"{spec.event_prefix}.downloaded",
        actor=actor,
        target_id=str(row.id),
        changes={spec.title_field: title, spec.category_field: str(getattr(row, spec.category_field) or "")},
    )


async def stream_file_content(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    file_id: uuid.UUID,
    for_download: bool,
    if_none_match: str | None = None,
) -> FileStreamResult:
    row = await require_file(session, spec, file_id)
    subject = preview_subject(spec, row)
    if not for_download:
        candidate_etag = common_preview.expected_preview_etag(subject)
        if candidate_etag is not None and common_preview.etag_matches(if_none_match, candidate_etag):
            return common_preview.not_modified_result(subject.filename, candidate_etag)

    settings = get_settings()
    if not for_download and subject.storage_path:
        office_ext = office_preview.office_extension(subject.filename, subject.file_suffix, subject.storage_path)
        if office_ext is not None or common_preview.is_pdf_subject(subject):
            await session.commit()
            pdf = await common_preview.open_preview_pdf(settings, subject, office_ext, not_found_msg=spec.not_found_msg)
            if pdf is not None and common_preview.etag_matches(if_none_match, pdf.etag):
                await storage.close_stream(pdf.stream)
                return common_preview.not_modified_result(subject.filename, pdf.etag)
            if pdf is not None:
                return FileStreamResult(
                    stream=pdf.stream,
                    filename=pdf.filename,
                    media_type=common_preview.PDF_MEDIA_TYPE,
                    content_length=pdf.size,
                    etag=pdf.etag,
                    ranged=True,
                )
        if office_ext is not None:
            raw = fallback_summary_text(spec, row).encode("utf-8")
            return FileStreamResult(
                stream=common_preview.single_chunk_stream(raw),
                filename=f"{subject.filename}.txt",
                media_type="text/plain; charset=utf-8",
                content_length=len(raw),
            )

    await session.commit()
    stream, filename, media_type, size, etag = await common_preview.open_storage_or_summary(
        settings,
        subject,
        for_download=for_download,
        fallback_bytes=lambda: fallback_summary_text(spec, row).encode("utf-8"),
    )
    if for_download:
        try:
            await _record_download_audit(session, spec, actor, row)
            await session.commit()
        except Exception:
            await storage.close_stream(stream)
            raise
    return FileStreamResult(stream=stream, filename=filename, media_type=media_type, content_length=size, etag=etag)


async def toggle_favorite(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    actor: Actor,
    file_id: uuid.UUID,
    favorite: bool,
) -> dict[str, Any]:
    row = await require_file(session, spec, file_id)
    title = str(getattr(row, spec.title_field) or "")
    changed = await repo.set_favorite(session, spec, user_id=actor.id, file_id=row.id, favorite=favorite)
    if changed:
        op_label = "收藏" if favorite else "取消收藏"
        event_type = f"{spec.event_prefix}.favorited" if favorite else f"{spec.event_prefix}.unfavorited"
        await repo.add_op_log(
            session,
            spec,
            file_id=row.id,
            actor=actor,
            op_type=op_label,
            detail=f"{op_label}{spec.item_noun}「{title}」",
        )
        await enqueue_event(
            session,
            event_type=event_type,
            actor=actor,
            target_id=str(row.id),
            changes={spec.title_field: title, "is_favorited": favorite},
        )
    return {"id": str(row.id), "is_favorited": favorite}


async def list_logs(
    session: AsyncSession,
    spec: LibrarySpec,
    *,
    file_id: uuid.UUID,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    row = await require_file(session, spec, file_id)
    items, total = await repo.list_op_logs(session, spec, file_id=row.id, page=page, page_size=page_size)
    return {"items": [_log_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


def schedule_upload_warmup(tasks: BackgroundTasks, settings: Any, slug: str, file_id: str) -> bool:
    if not settings.preview_warmup_on_upload:
        return False
    tasks.add_task(warm_preview, slug, uuid.UUID(file_id))
    return True


def _warm_skip_reason(subject: PreviewSubject | None, office_ext: str | None) -> str | None:
    if subject is None:
        return "deleted"
    if not subject.storage_path:
        return "no_source"
    if office_ext is None and not common_preview.is_pdf_subject(subject):
        return "not_previewable"
    if office_ext is not None and not office_preview.has_libreoffice():
        return "no_libreoffice"
    return None if preview_slots.has_free_slot() else "busy"


async def _warm(settings: Any, spec: LibrarySpec, file_id: uuid.UUID, session_factory: SessionFactory) -> str:
    async with session_factory() as session:
        row = await repo.get_by_id(session, spec, file_id)
    subject = preview_subject(spec, row) if row is not None else None
    office_ext = (
        office_preview.office_extension(subject.filename, subject.file_suffix, subject.storage_path)
        if subject is not None
        else None
    )
    reason = _warm_skip_reason(subject, office_ext)
    if reason is not None or subject is None:
        return reason or "deleted"
    if await common_preview.preview_cached(settings, subject):
        return "cached"
    try:
        pdf = await common_preview.open_preview_pdf(
            settings, subject, office_ext, wait=False, not_found_msg=spec.not_found_msg
        )
    except preview_slots.SlotBusyError:
        return "busy"
    except NotFoundError:
        return "deleted"
    if pdf is None:
        return "unavailable"
    await storage.close_stream(pdf.stream)
    return "done"


async def warm_preview(slug: str, file_id: uuid.UUID, *, session_factory: SessionFactory = SessionLocal) -> None:
    spec = LIBRARY_SPECS.get(slug)
    if spec is None:
        return
    try:
        outcome = await _warm(get_settings(), spec, file_id, session_factory)
    except Exception as exc:  # noqa: BLE001  后台预热尽力而为，失败只记日志
        logger.warning("library_preview_warmup_failed", library=slug, file_id=str(file_id), error=str(exc))
        return
    if outcome == "done":
        logger.info("library_preview_warmup_done", library=slug, file_id=str(file_id))
    elif outcome == "unavailable":
        logger.warning("library_preview_warmup_failed", library=slug, file_id=str(file_id), error="preview_unavailable")
    else:
        logger.info("library_preview_warmup_skipped", library=slug, file_id=str(file_id), reason=outcome)
