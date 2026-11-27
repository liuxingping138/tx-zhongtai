"""我的收藏跨库仓储：仅查询当前用户有权限的子库，按收藏时间倒序合并分页。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from platform_common.filters import contains_ilike
from sqlalchemy import ColumnElement, String, cast, false, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.upload_utils import pipe_match
from app.favorites.domain.access import FavoritesAccess, FavoritesQuery
from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile
from app.knowledge.domain.scopes import KnowledgeAccess
from app.library.domain.models import ProposalFavorite, ProposalFile, ReportFavorite, ReportFile


@dataclass(frozen=True)
class FavoriteRow:
    id: Any
    library: str
    title: str
    category_label: str
    industry_label: str
    region_label: str
    file_suffix: str
    file_size_bytes: int
    favorited_at: datetime
    updated_at: datetime


def _knowledge_scope_conds(access: KnowledgeAccess) -> list[ColumnElement[bool]]:
    if not access.readable_file_types or not access.readable_industries:
        return [false()]
    ind_clauses: list[ColumnElement[bool]] = [
        pipe_match(KnowledgeFile.industry_type, ind) for ind in sorted(access.readable_industries)
    ]
    if "无" in access.readable_industries:
        ind_clauses.append(KnowledgeFile.industry_type == "")
    return [
        KnowledgeFile.file_type.in_(sorted(access.readable_file_types)),
        or_(*ind_clauses),
    ]


def _knowledge_conds(user_id: str, access: KnowledgeAccess, keyword: str) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [
        KnowledgeFavorite.user_id == user_id,
        *_knowledge_scope_conds(access),
    ]
    if keyword:
        conds.append(
            or_(
                contains_ilike(KnowledgeFile.file_name, keyword),
                contains_ilike(KnowledgeFile.file_type, keyword),
                contains_ilike(KnowledgeFile.industry_type, keyword),
                contains_ilike(KnowledgeFile.prov_name, keyword),
            )
        )
    return conds


def _report_conds(user_id: str, keyword: str) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [ReportFavorite.user_id == user_id]
    if keyword:
        conds.append(
            or_(
                contains_ilike(ReportFile.report_name, keyword),
                contains_ilike(ReportFile.report_type, keyword),
                contains_ilike(ReportFile.industry_tags, keyword),
                contains_ilike(ReportFile.region_tag, keyword),
                contains_ilike(ReportFile.customer_name, keyword),
            )
        )
    return conds


def _proposal_conds(user_id: str, keyword: str) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [ProposalFavorite.user_id == user_id]
    if keyword:
        conds.append(
            or_(
                contains_ilike(ProposalFile.proposal_name, keyword),
                contains_ilike(ProposalFile.proposal_type, keyword),
                contains_ilike(ProposalFile.industry_tags, keyword),
                contains_ilike(ProposalFile.region_tag, keyword),
                contains_ilike(ProposalFile.customer_name, keyword),
            )
        )
    return conds


def _knowledge_select(conds: list[ColumnElement[bool]]) -> Any:
    return (
        select(
            KnowledgeFile.id.label("id"),
            cast(literal("knowledge"), String(16)).label("library"),
            KnowledgeFile.file_name.label("title"),
            cast(KnowledgeFile.file_type, String(128)).label("category_label"),
            KnowledgeFile.industry_type.label("industry_label"),
            cast(KnowledgeFile.prov_name, String(128)).label("region_label"),
            KnowledgeFile.file_suffix.label("file_suffix"),
            KnowledgeFile.file_size_bytes.label("file_size_bytes"),
            KnowledgeFavorite.created_at.label("favorited_at"),
            KnowledgeFile.updated_at.label("updated_at"),
        )
        .join(KnowledgeFile, KnowledgeFile.id == KnowledgeFavorite.file_id)
        .where(*conds)
    )


def _report_select(conds: list[ColumnElement[bool]]) -> Any:
    return (
        select(
            ReportFile.id.label("id"),
            cast(literal("reports"), String(16)).label("library"),
            ReportFile.report_name.label("title"),
            cast(ReportFile.report_type, String(128)).label("category_label"),
            ReportFile.industry_tags.label("industry_label"),
            cast(ReportFile.region_tag, String(128)).label("region_label"),
            ReportFile.file_suffix.label("file_suffix"),
            ReportFile.file_size_bytes.label("file_size_bytes"),
            ReportFavorite.created_at.label("favorited_at"),
            ReportFile.updated_at.label("updated_at"),
        )
        .join(ReportFile, ReportFile.id == ReportFavorite.file_id)
        .where(*conds)
    )


def _proposal_select(conds: list[ColumnElement[bool]]) -> Any:
    return (
        select(
            ProposalFile.id.label("id"),
            cast(literal("proposals"), String(16)).label("library"),
            ProposalFile.proposal_name.label("title"),
            cast(ProposalFile.proposal_type, String(128)).label("category_label"),
            ProposalFile.industry_tags.label("industry_label"),
            cast(ProposalFile.region_tag, String(128)).label("region_label"),
            ProposalFile.file_suffix.label("file_suffix"),
            ProposalFile.file_size_bytes.label("file_size_bytes"),
            ProposalFavorite.created_at.label("favorited_at"),
            ProposalFile.updated_at.label("updated_at"),
        )
        .join(ProposalFile, ProposalFile.id == ProposalFavorite.file_id)
        .where(*conds)
    )


async def _count_join(session: AsyncSession, fav_model: Any, file_model: Any, conds: list[ColumnElement[bool]]) -> int:
    stmt = (
        select(func.count()).select_from(fav_model).join(file_model, file_model.id == fav_model.file_id).where(*conds)
    )
    return int(await session.scalar(stmt) or 0)


async def list_unified_favorites(
    session: AsyncSession,
    *,
    user_id: str,
    access: FavoritesAccess,
    query: FavoritesQuery,
) -> tuple[list[FavoriteRow], dict[str, int]]:
    q = (query.keyword or "").strip()
    counts: dict[str, int] = {"all": 0, "knowledge": 0, "reports": 0, "proposals": 0}
    selects: list[Any] = []

    if access.can_read_knowledge and access.knowledge is not None:
        k_conds = _knowledge_conds(user_id, access.knowledge, q)
        counts["knowledge"] = await _count_join(session, KnowledgeFavorite, KnowledgeFile, k_conds)
        if query.library in {"all", "knowledge"} and counts["knowledge"] > 0:
            selects.append(_knowledge_select(k_conds))

    if access.can_read_reports:
        r_conds = _report_conds(user_id, q)
        counts["reports"] = await _count_join(session, ReportFavorite, ReportFile, r_conds)
        if query.library in {"all", "reports"} and counts["reports"] > 0:
            selects.append(_report_select(r_conds))

    if access.can_read_proposals:
        p_conds = _proposal_conds(user_id, q)
        counts["proposals"] = await _count_join(session, ProposalFavorite, ProposalFile, p_conds)
        if query.library in {"all", "proposals"} and counts["proposals"] > 0:
            selects.append(_proposal_select(p_conds))

    counts["all"] = counts["knowledge"] + counts["reports"] + counts["proposals"]
    if not selects:
        return [], counts

    combined = union_all(*selects).subquery() if len(selects) > 1 else selects[0].subquery()
    stmt = (
        select(combined)
        .order_by(combined.c.favorited_at.desc(), combined.c.id.desc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    )
    rows = (await session.execute(stmt)).mappings().all()
    items = [
        FavoriteRow(
            id=row["id"],
            library=str(row["library"]),
            title=str(row["title"]),
            category_label=str(row["category_label"] or ""),
            industry_label=str(row["industry_label"] or ""),
            region_label=str(row["region_label"] or ""),
            file_suffix=str(row["file_suffix"] or ""),
            file_size_bytes=int(row["file_size_bytes"] or 0),
            favorited_at=row["favorited_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return items, counts
