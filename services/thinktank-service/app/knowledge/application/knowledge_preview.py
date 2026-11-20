"""知识库文件在线预览辅助：Office 转 PDF 缓存读取与文本摘要兜底。"""

from __future__ import annotations

import asyncio
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
