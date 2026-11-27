"""智库通用在线预览与缓存引擎：供资料库、报告库、方案库复用。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.logging_setup import get_logger

from app.core import office_preview, pdf_optimize, preview_cache, storage

logger = get_logger(__name__)

PDF_MEDIA_TYPE = "application/pdf"
_CACHE_VARIANT = "preview-v2"
_ETAG_OFFICE = "office-pdf-v2"
_ETAG_PDF = "pdf-v2"


@dataclass(frozen=True)
class PreviewSubject:
    """与具体 ORM 模型解耦的文件预览元数据视图。"""

    file_id: str
    filename: str
    file_suffix: str
    storage_path: str
    file_size_bytes: int


@dataclass(frozen=True)
class FileStreamResult:
    stream: AsyncIterator[bytes]
    filename: str
    media_type: str
    content_length: int | None = None
    etag: str | None = None
    not_modified: bool = False
    ranged: bool = False


@dataclass(frozen=True)
class PreviewPdf:
    """已打开的预览用 PDF：本地缓存文件，能按 Range 分段读。"""

    stream: preview_cache.FileChunks
    filename: str
    size: int
    etag: str


async def single_chunk_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


def not_modified_result(filename: str, etag: str) -> FileStreamResult:
    """条件请求命中（304）：不带正文。"""

    return FileStreamResult(
        stream=single_chunk_stream(b""), filename=filename, media_type="", etag=etag, not_modified=True
    )


def _storage_unavailable(exc: Exception) -> ApiError:
    return ApiError("文件存储服务暂不可用，请稍后重试", code=ErrorCode.DEPENDENCY_UNAVAILABLE, http_status=503)


def _source_writer(settings: Any, storage_path: str) -> office_preview.SourceWriter:
    async def write(target: Path) -> bool:
        try:
            opened = await storage.stream_object(settings, storage_path)
        except storage.StorageUnavailableError as exc:
            raise _storage_unavailable(exc) from exc
        if opened is None:
            return False
        stream, _size = opened
        try:
            with target.open("wb") as fp:
                async for chunk in stream:
                    await asyncio.to_thread(fp.write, chunk)
        except storage.StorageUnavailableError as exc:
            raise _storage_unavailable(exc) from exc
        finally:
            await storage.close_stream(stream)
        return True

    return write


def cache_dir(settings: Any) -> str:
    return str(Path(settings.storage_dir) / "preview_cache")


def cache_key(subject: PreviewSubject, variant: str = _CACHE_VARIANT) -> str:
    return preview_cache.cache_key_for(subject.file_id, subject.storage_path, subject.file_size_bytes, variant)


def _optimize_options(settings: Any) -> pdf_optimize.OptimizeOptions:
    return pdf_optimize.OptimizeOptions(
        compress_min_bytes=settings.preview_compress_min_bytes,
        dpi=settings.preview_compress_dpi,
        timeout_seconds=settings.preview_optimize_timeout_seconds,
    )


def is_pdf_subject(subject: PreviewSubject) -> bool:
    return storage.media_type_for_file(subject.filename, subject.file_suffix, subject.storage_path) == PDF_MEDIA_TYPE


def download_filename(title: str, file_suffix: str, storage_path: str) -> str:
    """下载文件名：标题不含原始扩展名时按不可变存储路径补回后缀，避免浏览器失去文件类型。"""

    stored_ext = storage.raw_extension(storage_path) if storage_path else ""
    if not stored_ext:
        return title
    if title.lower().endswith(f".{stored_ext.lower()}"):
        return title
    return f"{title}.{stored_ext.lower()}"


def preview_mode_for(subject: PreviewSubject) -> str:
    ext = storage.effective_extension(subject.filename, subject.file_suffix, subject.storage_path)
    is_office_pdf = (
        office_preview.office_extension(subject.filename, subject.file_suffix, subject.storage_path) is not None
        and office_preview.has_libreoffice()
    )
    if subject.storage_path and (ext == "PDF" or is_office_pdf):
        return "pdf"
    if subject.storage_path and ext in {"TXT", "MD", "CSV"}:
        return "text"
    return "summary"


async def prepare_preview_pdf(
    settings: Any,
    subject: PreviewSubject,
    office_ext: str | None,
    *,
    wait: bool,
    not_found_msg: str = "文件不存在",
) -> Path | None:
    cdir, ckey = cache_dir(settings), cache_key(subject)
    writer = _source_writer(settings, subject.storage_path)
    options = _optimize_options(settings)
    slot = pdf_optimize.CacheSlot(cdir, ckey, settings.preview_cache_max_bytes)
    try:
        if office_ext is not None:
            return await office_preview.convert_office_to_pdf(writer, office_ext, slot, optimize=options, wait=wait)
        return await pdf_optimize.prepare_pdf_preview(writer, slot, options, wait=wait)
    except preview_cache.FileDeletedError as exc:
        raise NotFoundError(not_found_msg) from exc


def preview_etag(subject: PreviewSubject, *, kind: str) -> str:
    digest = hashlib.sha256(
        f"{subject.file_id}:{subject.storage_path}:{subject.file_size_bytes}:{kind}".encode()
    ).hexdigest()[:24]
    return f'"{digest}"'


def etag_matches(if_none_match: str | None, etag: str | None) -> bool:
    if not if_none_match or not etag:
        return False
    target = etag.strip().removeprefix("W/").strip()
    for raw in if_none_match.split(","):
        tag = raw.strip()
        if tag == "*" or tag.removeprefix("W/").strip() == target:
            return True
    return False


def expected_preview_etag(subject: PreviewSubject) -> str | None:
    if not subject.storage_path or is_pdf_subject(subject):
        return None
    if office_preview.office_extension(subject.filename, subject.file_suffix, subject.storage_path) is not None:
        return None
    return preview_etag(subject, kind="raw")


async def open_preview_pdf(
    settings: Any,
    subject: PreviewSubject,
    office_ext: str | None,
    *,
    wait: bool = True,
    not_found_msg: str = "文件不存在",
) -> PreviewPdf | None:
    pdf_path = await prepare_preview_pdf(settings, subject, office_ext, wait=wait, not_found_msg=not_found_msg)
    if office_ext is not None:
        filename, kind = f"{Path(subject.filename).stem}.pdf", _ETAG_OFFICE
    else:
        filename, kind = download_filename(subject.filename, subject.file_suffix, subject.storage_path), _ETAG_PDF
    if pdf_path is None:
        return None
    opened = await asyncio.to_thread(preview_cache.open_pdf, pdf_path)
    if opened is None:
        return None
    stream, size = opened
    try:
        content = await asyncio.to_thread(stream.fingerprint)
    except OSError:
        await stream.aclose()
        raise
    return PreviewPdf(stream=stream, filename=filename, size=size, etag=preview_etag(subject, kind=f"{kind}:{content}"))


async def preview_cached(settings: Any, subject: PreviewSubject) -> bool:
    path = preview_cache.pdf_path(cache_dir(settings), cache_key(subject))
    return await asyncio.to_thread(path.is_file)


async def drop_preview_cache(settings: Any, subject: PreviewSubject) -> None:
    cdir = cache_dir(settings)
    try:
        for key in (cache_key(subject), cache_key(subject, variant="")):
            await asyncio.to_thread(preview_cache.remove, cdir, key)
    except OSError as exc:
        logger.warning("preview_cache_cleanup_failed", file_id=subject.file_id, error=str(exc))


async def open_storage_or_summary(
    settings: Any,
    subject: PreviewSubject,
    *,
    for_download: bool,
    fallback_bytes: Callable[[], bytes],
) -> tuple[AsyncIterator[bytes], str, str, int | None, str | None]:
    try:
        opened = await storage.stream_object(settings, subject.storage_path)
    except storage.StorageUnavailableError as exc:
        raise _storage_unavailable(exc) from exc
    if opened is not None:
        stream, size = opened
        media_type = storage.media_type_for_file(subject.filename, subject.file_suffix, subject.storage_path)
        etag = None if for_download else preview_etag(subject, kind="raw")
        filename = download_filename(subject.filename, subject.file_suffix, subject.storage_path)
        return stream, filename, media_type, size, etag
    raw = fallback_bytes()
    return single_chunk_stream(raw), f"{subject.filename}.txt", "text/plain; charset=utf-8", len(raw), None


async def close_file_stream(result: FileStreamResult) -> None:
    await storage.close_stream(result.stream)
