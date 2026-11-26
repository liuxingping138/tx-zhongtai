"""知识库文件在线预览辅助：预览用 PDF（Office 转出的、PDF 压缩线性化后的）的缓存读取与文本摘要兜底。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.logging_setup import get_logger

from app.core import office_preview, pdf_optimize, preview_cache, storage
from app.knowledge.domain.models import KnowledgeFile

logger = get_logger(__name__)

PDF_MEDIA_TYPE = "application/pdf"
# 预览缓存和 ETag 的形态标记：处理方式变了就换一个，旧缓存不再命中，浏览器里的旧副本也不再被 304 沿用。
_CACHE_VARIANT = "preview-v2"
_ETAG_OFFICE = "office-pdf-v2"
_ETAG_PDF = "pdf-v2"


@dataclass(frozen=True)
class FileStreamResult:
    stream: AsyncIterator[bytes]
    filename: str
    media_type: str
    content_length: int | None = None
    etag: str | None = None
    not_modified: bool = False
    # 流是本地缓存文件（preview_cache.FileChunks），可以按 HTTP Range 分段下发
    ranged: bool = False


def not_modified_result(filename: str, etag: str) -> FileStreamResult:
    """条件请求命中（304）：不带正文。"""

    return FileStreamResult(
        stream=single_chunk_stream(b""), filename=filename, media_type="", etag=etag, not_modified=True
    )


@dataclass(frozen=True)
class PreviewPdf:
    """已打开的预览用 PDF：本地缓存文件，能按 Range 分段读。"""

    stream: preview_cache.FileChunks
    filename: str
    size: int
    etag: str


def fallback_summary_bytes(row: KnowledgeFile) -> bytes:
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


def _storage_unavailable(exc: Exception) -> ApiError:
    return ApiError("文件存储服务暂不可用，请稍后重试", code=ErrorCode.DEPENDENCY_UNAVAILABLE, http_status=503)


def _source_writer(settings: Any, storage_path: str) -> office_preview.SourceWriter:
    """把源文件按块写进临时文件：存储连不上回 503，源文件不存在返回 False。"""

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


def _cache_dir(settings: Any) -> str:
    return str(Path(settings.storage_dir) / "preview_cache")


def _cache_key(row: KnowledgeFile, variant: str = _CACHE_VARIANT) -> str:
    return preview_cache.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes, variant)


def _optimize_options(settings: Any) -> pdf_optimize.OptimizeOptions:
    return pdf_optimize.OptimizeOptions(
        compress_min_bytes=settings.preview_compress_min_bytes,
        dpi=settings.preview_compress_dpi,
        timeout_seconds=settings.preview_optimize_timeout_seconds,
    )


def is_pdf_file(row: KnowledgeFile) -> bool:
    return storage.media_type_for_file(row.file_name, row.file_suffix, row.storage_path) == PDF_MEDIA_TYPE


async def _prepare(settings: Any, row: KnowledgeFile, office_ext: str | None, *, wait: bool) -> Path | None:
    cache_dir, cache_key = _cache_dir(settings), _cache_key(row)
    writer = _source_writer(settings, row.storage_path)
    options = _optimize_options(settings)
    slot = pdf_optimize.CacheSlot(cache_dir, cache_key, settings.preview_cache_max_bytes)
    try:
        if office_ext is not None:
            return await office_preview.convert_office_to_pdf(writer, office_ext, slot, optimize=options, wait=wait)
        return await pdf_optimize.prepare_pdf_preview(writer, slot, options, wait=wait)
    except preview_cache.FileDeletedError as exc:
        raise NotFoundError("知识文件不存在") from exc


async def open_preview_pdf(
    settings: Any, row: KnowledgeFile, office_ext: str | None, *, wait: bool = True
) -> PreviewPdf | None:
    """返回已打开的预览用 PDF：先查磁盘缓存，未命中时拉源文件，Office 由 LibreOffice 转码，再压缩、线性化。

    Office 转不出来、源文件不存在、PDF 最近写缓存失败过返回 None；转换途中文件被删了抛 NotFoundError。
    调用前先交还数据库连接：转码、压缩可能要一两分钟。
    `wait=False`（上传后的预热）：名额已满抛 `preview_slots.SlotBusyError`，不排队。
    """

    pdf_path = await _prepare(settings, row, office_ext, wait=wait)
    if office_ext is not None:
        filename, kind = f"{Path(row.file_name).stem}.pdf", _ETAG_OFFICE
    else:
        filename, kind = row.file_name, _ETAG_PDF
    if pdf_path is None:
        return None
    # 刚查到就被别的请求淘汰掉的极少见，当作这次没做出来。
    opened = await asyncio.to_thread(preview_cache.open_pdf, pdf_path)
    if opened is None:
        return None
    stream, size = opened
    # ETag 按缓存文件的实际内容算：淘汰后重做出来的字节不同，ETag 也跟着变，浏览器不会把新旧两份的 Range 拼在一起。
    try:
        content = await asyncio.to_thread(stream.fingerprint)
    except OSError:
        await stream.aclose()
        raise
    return PreviewPdf(stream=stream, filename=filename, size=size, etag=preview_etag(row, kind=f"{kind}:{content}"))


async def preview_cached(settings: Any, row: KnowledgeFile) -> bool:
    """预览用 PDF 已在缓存里（不记一次使用，免得预热把它排到最近用过）。"""

    path = preview_cache.pdf_path(_cache_dir(settings), _cache_key(row))
    return await asyncio.to_thread(path.is_file)


async def drop_preview_cache(settings: Any, row: KnowledgeFile) -> None:
    """删文件后清掉它的预览缓存（含改版前的旧形态）；清不掉只记日志，不影响删除（容量上限迟早会把它淘汰）。"""

    cache_dir = _cache_dir(settings)
    try:
        for key in (_cache_key(row), _cache_key(row, variant="")):
            await asyncio.to_thread(preview_cache.remove, cache_dir, key)
    except OSError as exc:
        logger.warning("preview_cache_cleanup_failed", file_id=str(row.id), error=str(exc))


def preview_etag(row: KnowledgeFile, *, kind: str) -> str:
    """基于文件标识、存储路径、大小与预览形态生成稳定 ETag，用于 private no-cache 条件协商。"""

    digest = hashlib.sha256(f"{row.id}:{row.storage_path}:{row.file_size_bytes}:{kind}".encode()).hexdigest()[:24]
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


def expected_preview_etag(row: KnowledgeFile) -> str | None:
    """不打开文件就能算出的 ETag（文本等对象存储直读的原文件）。

    预览用 PDF（PDF、Office 转出的）的 ETag 按缓存文件内容算，要打开缓存后才知道，这里返回 None。
    """

    if not row.storage_path or is_pdf_file(row):
        return None
    if office_preview.office_extension(row.file_name, row.file_suffix, row.storage_path) is not None:
        return None
    return preview_etag(row, kind="raw")


async def single_chunk_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def open_storage_or_summary(
    settings: Any, row: KnowledgeFile, *, for_download: bool
) -> tuple[AsyncIterator[bytes], str, str, int | None, str | None]:
    try:
        opened = await storage.stream_object(settings, row.storage_path)
    except storage.StorageUnavailableError as exc:
        raise _storage_unavailable(exc) from exc
    if opened is not None:
        stream, size = opened
        media_type = storage.media_type_for_file(row.file_name, row.file_suffix, row.storage_path)
        etag = None if for_download else preview_etag(row, kind="raw")
        return stream, row.file_name, media_type, size, etag
    raw = fallback_summary_bytes(row)
    return single_chunk_stream(raw), f"{row.file_name}.txt", "text/plain; charset=utf-8", len(raw), None
