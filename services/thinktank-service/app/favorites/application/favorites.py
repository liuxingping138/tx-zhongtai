"""我的收藏应用用例：汇总当前用户有权限的资料库、报告库、方案库收藏。"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.upload_utils import format_size
from app.favorites.domain.access import LIBRARY_LABELS, FavoritesAccess, FavoritesQuery
from app.favorites.repositories import favorites as repo
from app.favorites.repositories.favorites import FavoriteRow


def _can_download(row: FavoriteRow, access: FavoritesAccess) -> bool:
    if row.library == "knowledge":
        if access.knowledge is None:
            return False
        return access.knowledge.can_download_record(row.category_label, row.industry_label)
    if row.library == "reports":
        return access.reports_can_download
    if row.library == "proposals":
        return access.proposals_can_download
    return False


def _can_export(row: FavoriteRow, access: FavoritesAccess) -> bool:
    if row.library == "knowledge":
        if access.knowledge is None:
            return False
        return access.knowledge.can_export_record(row.category_label, row.industry_label)
    if row.library == "reports":
        return access.reports_can_export
    if row.library == "proposals":
        return access.proposals_can_export
    return False


def _entry_out(row: FavoriteRow, access: FavoritesAccess) -> dict[str, Any]:
    category = (row.category_label or "未定义") if row.library == "knowledge" else row.category_label
    return {
        "id": str(row.id),
        "library": row.library,
        "library_label": LIBRARY_LABELS.get(row.library, row.library),
        "title": row.title,
        "category_label": category,
        "industry_label": row.industry_label,
        "region_label": row.region_label,
        "file_suffix": row.file_suffix,
        "file_size_display": format_size(row.file_size_bytes),
        "favorited_at": format_beijing(row.favorited_at),
        "updated_at": format_beijing(row.updated_at),
        "can_download": _can_download(row, access),
        "can_export": _can_export(row, access),
        "preview_path": f"/thinktank/{row.library}/{row.id}",
    }


async def list_favorites(
    session: AsyncSession,
    *,
    actor: Actor,
    access: FavoritesAccess,
    query: FavoritesQuery,
) -> dict[str, Any]:
    rows, counts = await repo.list_unified_favorites(session, user_id=actor.id, access=access, query=query)
    return {
        "items": [_entry_out(row, access) for row in rows],
        "total": counts.get(query.library, 0),
        "page": query.page,
        "page_size": query.page_size,
        "counts": counts,
    }
