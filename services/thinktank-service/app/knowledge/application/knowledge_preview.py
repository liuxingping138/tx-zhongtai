"""知识库文件在线预览辅助：Office 转 PDF 缓存读取与文本摘要兜底。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_common.errors import ApiError, ErrorCode

from app.core import office_preview, storage
from app.knowledge.domain.models import KnowledgeFile


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


async def load_office_preview_pdf(settings: Any, row: KnowledgeFile, office_ext: str) -> bytes | None:
    """优先读磁盘缓存 PDF；未命中时拉取 MinIO 源文件并由 LibreOffice 转码缓存。"""

    cache_dir = str(Path(settings.storage_dir) / "preview_cache")
    cache_key = office_preview.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes)
    cached_pdf = await office_preview.read_cached_pdf(cache_dir, cache_key)
    if cached_pdf is not None:
        return cached_pdf
    try:
        raw = await storage.read_object(settings, row.storage_path)
    except storage.StorageUnavailableError as exc:
        raise ApiError(
            "文件存储服务暂不可用，请稍后重试",
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            http_status=503,
        ) from exc
    if raw is None:
        return None
    return await office_preview.convert_office_to_pdf(raw, office_ext, cache_dir=cache_dir, cache_key=cache_key)
