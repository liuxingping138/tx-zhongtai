"""智库统计应用服务：拼装全局资产结构、分类多维分布、行为趋势与排行榜。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.clock import format_beijing, utcnow
from platform_common.errors import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.statistics.domain.specs import (
    ALL_LIBRARIES,
    DIMENSIONS_BY_SCOPE,
    LIBRARY_LABELS,
    LibraryKey,
    StatisticsQuery,
    aggregate_classification_counts,
    compute_delta_pct,
    format_human_size,
    libraries_for_scope,
    resolve_time_window,
)
from app.statistics.repositories import statistics as repo


def _serialize_doc(doc: repo.RankedDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "library": doc.library,
        "library_label": LIBRARY_LABELS[doc.library],
        "title": doc.title,
        "category": doc.category,
        "industry": doc.industry,
        "dept": doc.dept,
        "file_suffix": doc.file_suffix,
        "file_size_bytes": doc.file_size_bytes,
        "file_size_display": format_human_size(doc.file_size_bytes),
        "uploader": doc.uploader,
        "uploaded_at": format_beijing(doc.uploaded_at),
        "is_defined": doc.is_defined,
        "downloads": doc.downloads,
        "previews": doc.previews,
        "favorites": doc.favorites,
    }


def _serialize_actor(actor: repo.RankedActor) -> dict[str, Any]:
    return {
        "actor_id": actor.actor_id,
        "name": actor.name,
        "uploads": actor.uploads,
        "governance": actor.governance,
        "previews": actor.previews,
        "downloads": actor.downloads,
        "active_days": actor.active_days,
    }


def _pct(part: int, whole: int) -> float:
    return round((part * 100.0) / whole, 1) if whole > 0 else 0.0


async def get_statistics_overview(
    session: AsyncSession,
    *,
    query: StatisticsQuery,
) -> dict[str, Any]:
    library = query.library
    granularity = query.granularity
    now = utcnow()
    window = resolve_time_window(preset=query.preset, date_from=query.date_from, date_to=query.date_to, now_utc=now)
    libs = libraries_for_scope(library)

    lib_totals = await repo.fetch_library_totals(session)
    all_files = sum(t.files for t in lib_totals.values())
    scope_files = sum(lib_totals[k].files for k in libs)
    scope_defined = sum(lib_totals[k].defined for k in libs)
    scope_bytes = sum(lib_totals[k].size_bytes for k in libs)

    cur_behavior = await repo.fetch_behavior_summary(
        session, libraries=libs, start_utc=window.start_utc, end_utc=window.end_utc
    )
    prev_behavior = (
        await repo.fetch_behavior_summary(
            session, libraries=libs, start_utc=window.prev_start_utc, end_utc=window.prev_end_utc
        )
        if window.prev_start_utc is not None and window.prev_end_utc is not None
        else None
    )

    # 拉取当前库视角下全部分类维度（前端切分类 Tab 零等待）
    dimensions_payload: list[dict[str, Any]] = []
    for spec in DIMENSIONS_BY_SCOPE[library]:
        raw_counts = await repo.fetch_dimension_raw_counts(session, libraries=libs, dimension_key=spec.key)
        aggregated = aggregate_classification_counts(raw_counts, spec=spec, limit=12)
        dim_total = sum(v for _, v in aggregated)
        dimensions_payload.append(
            {
                "key": spec.key,
                "label": spec.label,
                "note": spec.note,
                "show_win_banner": spec.show_win_banner,
                "drill_field": spec.drill_field,
                "total": dim_total,
                "items": [
                    {"name": name, "count": count, "share_pct": _pct(count, dim_total)} for name, count in aggregated
                ],
            }
        )

    proposal_win = await repo.fetch_proposal_win_summary(session) if "proposals" in libs else None
    trend = await repo.fetch_trend_series(
        session,
        libraries=libs,
        start_utc=window.start_utc,
        end_utc=window.end_utc,
        granularity=granularity,
    )
    top_docs = await repo.fetch_top_documents_by_metrics(
        session, libraries=libs, start_utc=window.start_utc, end_utc=window.end_utc, limit=10
    )
    uploaders, learners = await repo.fetch_top_actors(
        session, libraries=libs, start_utc=window.start_utc, end_utc=window.end_utc, limit=10
    )
    departments = await repo.fetch_top_departments(session, libraries=libs, limit=10)

    return {
        "as_of": format_beijing(now),
        "library": library,
        "granularity": granularity,
        "window": {
            "preset": window.preset,
            "date_from": window.date_from,
            "date_to": window.date_to,
            "days": window.days,
        },
        "assets": {
            "total_files": scope_files,
            "defined_files": scope_defined,
            "undefined_files": max(0, scope_files - scope_defined),
            "defined_rate": _pct(scope_defined, scope_files),
            "total_size_bytes": scope_bytes,
            "total_size_display": format_human_size(scope_bytes),
            "libraries": [
                {
                    "key": k,
                    "label": LIBRARY_LABELS[k],
                    "files": lib_totals[k].files,
                    "defined": lib_totals[k].defined,
                    "defined_rate": _pct(lib_totals[k].defined, lib_totals[k].files),
                    "share_pct": _pct(lib_totals[k].files, all_files),
                    "size_bytes": lib_totals[k].size_bytes,
                    "size_display": format_human_size(lib_totals[k].size_bytes),
                }
                for k in ALL_LIBRARIES
            ],
        },
        "behavior": {
            "uploads": cur_behavior.uploads,
            "uploads_delta_pct": compute_delta_pct(
                cur_behavior.uploads, prev_behavior.uploads if prev_behavior else None
            ),
            "governance": cur_behavior.governance,
            "previews": cur_behavior.previews,
            "previews_delta_pct": compute_delta_pct(
                cur_behavior.previews, prev_behavior.previews if prev_behavior else None
            ),
            "downloads": cur_behavior.downloads,
            "downloads_delta_pct": compute_delta_pct(
                cur_behavior.downloads, prev_behavior.downloads if prev_behavior else None
            ),
            "favorites_net": cur_behavior.favorites - cur_behavior.unfavorites,
            "favorites_added": cur_behavior.favorites,
            "active_users": cur_behavior.active_users,
            "active_users_delta_pct": compute_delta_pct(
                cur_behavior.active_users, prev_behavior.active_users if prev_behavior else None
            ),
        },
        "dimensions": dimensions_payload,
        "proposal_win": (
            {
                "total": proposal_win.total,
                "won": proposal_win.won,
                "lost": proposal_win.lost,
                "pending": proposal_win.pending,
                "aborted": proposal_win.aborted,
                "win_rate": proposal_win.win_rate,
                "win_amount_wan": proposal_win.win_amount_wan,
            }
            if proposal_win is not None
            else None
        ),
        "trend": [
            {
                "bucket_key": b.bucket_key,
                "label": b.label,
                "knowledge_uploads": b.knowledge_uploads,
                "reports_uploads": b.reports_uploads,
                "proposals_uploads": b.proposals_uploads,
                "total_uploads": b.knowledge_uploads + b.reports_uploads + b.proposals_uploads,
                "governance": b.governance,
                "previews": b.previews,
                "downloads": b.downloads,
                "active_users": b.active_users,
            }
            for b in trend
        ],
        "top_documents": {
            "download": [_serialize_doc(d) for d in top_docs["download"]],
            "preview": [_serialize_doc(d) for d in top_docs["preview"]],
            "favorite": [_serialize_doc(d) for d in top_docs["favorite"]],
        },
        "top_contributors": {
            "upload": [_serialize_actor(a) for a in uploaders],
            "active": [_serialize_actor(a) for a in learners],
            "dept": [
                {
                    "name": d.name,
                    "files": d.files,
                    "defined": d.defined,
                    "defined_rate": _pct(d.defined, d.files),
                }
                for d in departments
            ],
        },
    }


async def get_document_detail(
    session: AsyncSession,
    *,
    library: LibraryKey,
    file_id: uuid.UUID,
) -> dict[str, Any]:
    data = await repo.fetch_document_peek(session, library=library, file_id=file_id)
    if data is None:
        raise NotFoundError("文档不存在或已删除")
    return {
        "document": _serialize_doc(data.doc),
        "recent_logs": [
            {
                "actor_name": item.actor_name,
                "op_type": item.op_type,
                "detail": item.detail,
                "created_at": format_beijing(item.created_at),
            }
            for item in data.recent_logs
        ],
    }
