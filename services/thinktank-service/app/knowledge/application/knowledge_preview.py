"""知识库文件在线预览辅助：Office 转 PDF 缓存读取与文本摘要兜底。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from platform_common.errors import ApiError, ErrorCode
from platform_common.logging_setup import get_logger

from app.core import office_preview, preview_cache, storage
from app.knowledge.domain.models import KnowledgeFile

logger = get_logger(__name__)


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


def _cache_location(settings: Any, row: KnowledgeFile) -> tuple[str, str]:
    cache_dir = str(Path(settings.storage_dir) / "preview_cache")
    return cache_dir, preview_cache.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes)


async def open_office_preview_pdf(
    settings: Any, row: KnowledgeFile, office_ext: str
) -> tuple[preview_cache.FileChunks, int] | None:
    """返回已打开的 PDF 流和大小：先查磁盘缓存，未命中时拉源文件由 LibreOffice 转码。转不出来返回 None。"""

    cache_dir, cache_key = _cache_location(settings, row)
    pdf_path = await office_preview.convert_office_to_pdf(
        _source_writer(settings, row.storage_path),
        office_ext,
        cache_dir=cache_dir,
        cache_key=cache_key,
        max_cache_bytes=settings.preview_cache_max_bytes,
    )
    if pdf_path is None:
        return None
    # 刚查到就被别的请求淘汰掉的极少见，当作这次没转出来，回摘要。
    return await asyncio.to_thread(preview_cache.open_pdf, pdf_path)


async def drop_preview_cache(settings: Any, row: KnowledgeFile) -> None:
    """删文件后清掉它的预览缓存；清不掉只记日志，不影响删除（容量上限迟早会把它淘汰）。"""

    cache_dir, cache_key = _cache_location(settings, row)
    try:
        await asyncio.to_thread(preview_cache.remove, cache_dir, cache_key)
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
    if not row.storage_path:
        return None
    office_ext = office_preview.office_extension(row.file_name, row.file_suffix)
    return preview_etag(row, kind="office-pdf" if office_ext is not None else "raw")


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
        media_type = storage.media_type_for_file(row.file_name, row.file_suffix)
        etag = None if for_download else preview_etag(row, kind="raw")
        return stream, row.file_name, media_type, size, etag
    raw = fallback_summary_bytes(row)
    return single_chunk_stream(raw), f"{row.file_name}.txt", "text/plain; charset=utf-8", len(raw), None
