"""资料库文件在线预览辅助：复用 app.common.preview 通用预览与缓存引擎。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.common import preview as common_preview
from app.common.preview import (
    PDF_MEDIA_TYPE,
    FileStreamResult,
    PreviewPdf,
    PreviewSubject,
    etag_matches,
    not_modified_result,
    single_chunk_stream,
)
from app.core import office_preview, pdf_optimize, preview_cache, storage
from app.knowledge.domain.models import KnowledgeFile

__all__ = [
    "PDF_MEDIA_TYPE",
    "FileStreamResult",
    "PreviewPdf",
    "drop_preview_cache",
    "etag_matches",
    "expected_preview_etag",
    "fallback_summary_bytes",
    "is_pdf_file",
    "not_modified_result",
    "office_preview",
    "open_preview_pdf",
    "open_storage_or_summary",
    "pdf_optimize",
    "preview_cache",
    "preview_cached",
    "preview_etag",
    "single_chunk_stream",
    "storage",
]


def _subject(row: KnowledgeFile) -> PreviewSubject:
    return PreviewSubject(
        file_id=str(row.id),
        filename=row.file_name,
        file_suffix=row.file_suffix,
        storage_path=row.storage_path,
        file_size_bytes=row.file_size_bytes,
    )


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
        row.content_text or "（示例资料摘要）",
    ]
    return "\n".join(lines).encode("utf-8")


def is_pdf_file(row: KnowledgeFile) -> bool:
    return common_preview.is_pdf_subject(_subject(row))


async def open_preview_pdf(
    settings: Any, row: KnowledgeFile, office_ext: str | None, *, wait: bool = True
) -> PreviewPdf | None:
    return await common_preview.open_preview_pdf(
        settings, _subject(row), office_ext, wait=wait, not_found_msg="资料文件不存在"
    )


async def preview_cached(settings: Any, row: KnowledgeFile) -> bool:
    return await common_preview.preview_cached(settings, _subject(row))


async def drop_preview_cache(settings: Any, row: KnowledgeFile) -> None:
    await common_preview.drop_preview_cache(settings, _subject(row))


def preview_etag(row: KnowledgeFile, *, kind: str) -> str:
    return common_preview.preview_etag(_subject(row), kind=kind)


def expected_preview_etag(row: KnowledgeFile) -> str | None:
    return common_preview.expected_preview_etag(_subject(row))


async def open_storage_or_summary(
    settings: Any, row: KnowledgeFile, *, for_download: bool
) -> tuple[AsyncIterator[bytes], str, str, int | None, str | None]:
    return await common_preview.open_storage_or_summary(
        settings, _subject(row), for_download=for_download, fallback_bytes=lambda: fallback_summary_bytes(row)
    )
