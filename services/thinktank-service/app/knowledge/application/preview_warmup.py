"""上传后在后台预热预览缓存：第一个打开的人也能直接按 Range 读本地缓存，不用等转码、压缩。

- 由上传接口用 `BackgroundTasks` 排上：响应发出、上传事务已提交之后才跑，上传本身不多等一秒。
- 尽力而为：转码 / 压缩名额被占着（有人正在看）、文件被删、类型不需要预览、已有缓存都直接跳过；
  名额在真正要拿的那一刻再看一次（`wait=False`），满了就跳过、不排队，不会排在之后打开预览的人前面。
  做失败只记日志，任何异常都不往外抛（后台任务没人接得住）。
- 用的是和打开预览同一条流水线（`open_preview_pdf`：同一文件只做一次、转码和压缩合计同时最多 2 个），
  之后打开预览直接命中缓存。
- 自己开一个短会话读这一行，读完立刻交还连接，转码、压缩期间不占数据库连接。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks
from platform_common.errors import NotFoundError
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import office_preview, preview_slots, storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.knowledge.application.knowledge_preview import is_pdf_file, open_preview_pdf, preview_cached
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.repositories import knowledge as repo

logger = get_logger(__name__)

SessionFactory = Callable[[], AsyncSession]


def schedule_upload_warmup(tasks: BackgroundTasks, settings: Any, file_id: str) -> bool:
    """开关打开时排一次预热；返回是否排上。"""

    if not settings.preview_warmup_on_upload:
        return False
    tasks.add_task(warm_preview, uuid.UUID(file_id))
    return True


async def _load(session_factory: SessionFactory, file_id: uuid.UUID) -> KnowledgeFile | None:
    async with session_factory() as session:
        return await repo.get_by_id(session, file_id)


def _skip_reason(row: KnowledgeFile | None, office_ext: str | None) -> str | None:
    if row is None:
        return "deleted"
    if not row.storage_path:
        return "no_source"
    if office_ext is None and not is_pdf_file(row):
        return "not_previewable"
    if office_ext is not None and not office_preview.has_libreoffice():
        return "no_libreoffice"
    return None if preview_slots.has_free_slot() else "busy"


async def _warm(settings: Any, file_id: uuid.UUID, session_factory: SessionFactory) -> str:
    """做一次预热，返回结果：done，或跳过的原因。"""

    row = await _load(session_factory, file_id)
    office_ext = office_preview.office_extension(row.file_name, row.file_suffix) if row is not None else None
    reason = _skip_reason(row, office_ext)
    if reason is not None or row is None:
        return reason or "deleted"
    if await preview_cached(settings, row):
        return "cached"
    try:
        pdf = await open_preview_pdf(settings, row, office_ext, wait=False)
    except preview_slots.SlotBusyError:
        return "busy"  # 读行、查缓存的这一会儿名额被人拿走了
    except NotFoundError:
        return "deleted"  # 做的途中文件被删了，结果没有留进缓存
    if pdf is None:
        return "unavailable"
    await storage.close_stream(pdf.stream)
    return "done"


async def warm_preview(file_id: uuid.UUID, *, session_factory: SessionFactory = SessionLocal) -> None:
    """后台任务入口：不抛异常，结果只进日志。"""

    try:
        outcome = await _warm(get_settings(), file_id, session_factory)
    except Exception as exc:  # noqa: BLE001  后台预热尽力而为，失败只记日志，打开预览时会再做一次
        logger.warning("preview_warmup_failed", file_id=str(file_id), error=str(exc))
        return
    if outcome == "done":
        logger.info("preview_warmup_done", file_id=str(file_id))
    elif outcome == "unavailable":
        # 转码失败、源文件不存在或写缓存失败：流水线已记失败标记，打开预览时按原有方式回退
        logger.warning("preview_warmup_failed", file_id=str(file_id), error="preview_unavailable")
    else:
        logger.info("preview_warmup_skipped", file_id=str(file_id), reason=outcome)
