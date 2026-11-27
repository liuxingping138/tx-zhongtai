"""智库统计排行榜与单文档动态速览仓储。"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.statistics.domain.specs import LibraryKey
from app.statistics.repositories.overview import (
    FAV_MODELS,
    FILE_MODELS,
    LOG_MODELS,
    file_columns_map,
    logs_union_subquery,
)

_MetaTuple = tuple[str, str, str, str, str, int, str, datetime, bool]


@dataclass(frozen=True)
class RankedDocument:
    id: str
    library: LibraryKey
    title: str
    category: str
    industry: str
    dept: str
    file_suffix: str
    file_size_bytes: int
    uploader: str
    uploaded_at: datetime
    is_defined: bool
    downloads: int
    previews: int
    favorites: int


@dataclass(frozen=True)
class RankedActor:
    actor_id: str
    name: str
    uploads: int
    governance: int
    previews: int
    downloads: int
    active_days: int


@dataclass(frozen=True)
class RankedDepartment:
    name: str
    files: int
    defined: int


@dataclass(frozen=True)
class DocumentActivityItem:
    actor_name: str
    op_type: str
    detail: str
    created_at: datetime


@dataclass(frozen=True)
class DocumentPeekData:
    doc: RankedDocument
    recent_logs: list[DocumentActivityItem]


async def _fetch_file_meta_map(
    session: AsyncSession,
    keys_by_lib: dict[LibraryKey, set[uuid.UUID]],
) -> dict[tuple[LibraryKey, uuid.UUID], _MetaTuple]:
    meta: dict[tuple[LibraryKey, uuid.UUID], _MetaTuple] = {}
    for lib, ids in keys_by_lib.items():
        if not ids:
            continue
        model = FILE_MODELS[lib]
        cols = file_columns_map(lib)
        stmt = select(
            model.id,
            cols["title"],
            cols["category"],
            cols["industry"],
            cols["dept"],
            model.file_suffix,
            model.file_size_bytes,
            model.created_by_name,
            model.uploaded_at,
            model.is_defined,
        ).where(model.id.in_(ids))
        for row in (await session.execute(stmt)).all():
            meta[(lib, row[0])] = (
                str(row[1] or ""),
                str(row[2] or "") or "未定义",
                str(row[3] or "") or "无",
                str(row[4] or "") or "未填写",
                str(row[5] or ""),
                int(row[6] or 0),
                str(row[7] or ""),
                row[8],
                bool(row[9]),
            )
    return meta


def _rank_top_doc_keys(
    raw_stats: dict[tuple[LibraryKey, uuid.UUID], tuple[int, int, int]],
    fav_totals: dict[tuple[LibraryKey, uuid.UUID], int],
    *,
    metric_idx: int,
    limit: int,
    use_total_fav: bool = False,
) -> list[tuple[LibraryKey, uuid.UUID]]:
    scored = []
    for k, vals in raw_stats.items():
        score = fav_totals.get(k, vals[2]) if use_total_fav else vals[metric_idx]
        if score > 0:
            scored.append((score, vals[1], k))
    scored.sort(key=lambda x: (-x[0], -x[1], str(x[2][1])))
    return [x[2] for x in scored[:limit]]


def _materialize_docs(
    keys: list[tuple[LibraryKey, uuid.UUID]],
    meta_map: dict[tuple[LibraryKey, uuid.UUID], _MetaTuple],
    raw_stats: dict[tuple[LibraryKey, uuid.UUID], tuple[int, int, int]],
    fav_totals: dict[tuple[LibraryKey, uuid.UUID], int],
) -> list[RankedDocument]:
    items: list[RankedDocument] = []
    for k in keys:
        m = meta_map.get(k)
        if m is None:
            continue
        dl, pv, period_fav = raw_stats.get(k, (0, 0, 0))
        items.append(
            RankedDocument(
                id=str(k[1]),
                library=k[0],
                title=m[0],
                category=m[1],
                industry=m[2],
                dept=m[3],
                file_suffix=m[4],
                file_size_bytes=m[5],
                uploader=m[6],
                uploaded_at=m[7],
                is_defined=m[8],
                downloads=dl,
                previews=pv,
                favorites=fav_totals.get(k, period_fav),
            )
        )
    return items


async def fetch_top_documents_by_metrics(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    start_utc: datetime | None,
    end_utc: datetime,
    limit: int = 10,
) -> dict[str, list[RankedDocument]]:
    """一次查询返回下载榜、预览榜、收藏榜 TOP N 文档及元数据。"""

    logs = logs_union_subquery(libraries, start_utc, end_utc)
    agg_stmt = select(
        logs.c.library,
        logs.c.file_id,
        func.coalesce(func.sum(case((logs.c.op_type == "下载", 1), else_=0)), 0).label("downloads"),
        func.coalesce(func.sum(case((logs.c.op_type == "预览", 1), else_=0)), 0).label("previews"),
        func.coalesce(func.sum(case((logs.c.op_type == "收藏", 1), else_=0)), 0).label("favorites"),
    ).group_by(logs.c.library, logs.c.file_id)

    raw_stats: dict[tuple[LibraryKey, uuid.UUID], tuple[int, int, int]] = {
        (lib_str, fid): (int(dl), int(pv), int(fav))
        for lib_str, fid, dl, pv, fav in (await session.execute(agg_stmt)).all()
    }
    fav_totals: dict[tuple[LibraryKey, uuid.UUID], int] = {}
    for lib in libraries:
        fmodel = FAV_MODELS[lib]
        for fid, cnt in (await session.execute(select(fmodel.file_id, func.count()).group_by(fmodel.file_id))).all():
            fav_totals[(lib, fid)] = int(cnt)
            raw_stats.setdefault((lib, fid), (0, 0, 0))

    dl_keys = _rank_top_doc_keys(raw_stats, fav_totals, metric_idx=0, limit=limit)
    pv_keys = _rank_top_doc_keys(raw_stats, fav_totals, metric_idx=1, limit=limit)
    fav_keys = _rank_top_doc_keys(raw_stats, fav_totals, metric_idx=2, limit=limit, use_total_fav=True)

    needed: dict[LibraryKey, set[uuid.UUID]] = defaultdict(set)
    for lib_k, fid in (*dl_keys, *pv_keys, *fav_keys):
        needed[lib_k].add(fid)
    meta_map = await _fetch_file_meta_map(session, needed)
    return {
        "download": _materialize_docs(dl_keys, meta_map, raw_stats, fav_totals),
        "preview": _materialize_docs(pv_keys, meta_map, raw_stats, fav_totals),
        "favorite": _materialize_docs(fav_keys, meta_map, raw_stats, fav_totals),
    }


async def fetch_top_actors(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    start_utc: datetime | None,
    end_utc: datetime,
    limit: int = 10,
) -> tuple[list[RankedActor], list[RankedActor]]:
    """一次查询返回「上传贡献榜」与「高频使用榜」TOP N 人员。"""

    logs = logs_union_subquery(libraries, start_utc, end_utc)
    bj_day = cast(func.date_trunc("day", func.timezone("Asia/Shanghai", logs.c.created_at)), String)
    stmt = select(
        logs.c.actor_id,
        func.max(logs.c.actor_name).label("actor_name"),
        func.coalesce(func.sum(case((logs.c.op_type == "上传", 1), else_=0)), 0).label("uploads"),
        func.coalesce(func.sum(case((logs.c.op_type.in_(("上传标签", "编辑")), 1), else_=0)), 0).label("governance"),
        func.coalesce(func.sum(case((logs.c.op_type == "预览", 1), else_=0)), 0).label("previews"),
        func.coalesce(func.sum(case((logs.c.op_type == "下载", 1), else_=0)), 0).label("downloads"),
        func.count(func.distinct(bj_day)).label("active_days"),
    ).group_by(logs.c.actor_id)

    actors = [
        RankedActor(
            actor_id=str(row[0] or ""),
            name=str(row[1] or "").strip() or str(row[0] or "未知用户"),
            uploads=int(row[2] or 0),
            governance=int(row[3] or 0),
            previews=int(row[4] or 0),
            downloads=int(row[5] or 0),
            active_days=int(row[6] or 0),
        )
        for row in (await session.execute(stmt)).all()
    ]

    uploaders = sorted(
        [a for a in actors if a.uploads > 0 or a.governance > 0],
        key=lambda a: (-a.uploads, -a.governance, a.name),
    )[:limit]
    learners = sorted(
        [a for a in actors if a.previews > 0 or a.downloads > 0],
        key=lambda a: (-(a.previews + a.downloads * 3), -a.downloads, a.name),
    )[:limit]
    return uploaders, learners


async def fetch_top_departments(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    limit: int = 10,
) -> list[RankedDepartment]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for lib in libraries:
        model = FILE_MODELS[lib]
        dept_col = file_columns_map(lib)["dept"]
        stmt = select(
            dept_col,
            func.count(model.id),
            func.coalesce(func.sum(case((model.is_defined.is_(True), 1), else_=0)), 0),
        ).group_by(dept_col)
        for dept_val, cnt, defined_cnt in (await session.execute(stmt)).all():
            key = (str(dept_val or "").strip()) or "未归属部门"
            totals[key][0] += int(cnt)
            totals[key][1] += int(defined_cnt)

    ranked = [RankedDepartment(name=k, files=v[0], defined=v[1]) for k, v in totals.items() if v[0] > 0]
    ranked.sort(key=lambda d: (-d.files, -d.defined, d.name))
    return ranked[:limit]


async def fetch_document_peek(
    session: AsyncSession,
    *,
    library: LibraryKey,
    file_id: uuid.UUID,
) -> DocumentPeekData | None:
    meta = (await _fetch_file_meta_map(session, {library: {file_id}})).get((library, file_id))
    if meta is None:
        return None

    lmodel = LOG_MODELS[library]
    fmodel = FAV_MODELS[library]
    op_rows = (
        await session.execute(
            select(lmodel.op_type, func.count()).where(lmodel.file_id == file_id).group_by(lmodel.op_type)
        )
    ).all()
    counts = {str(op): int(cnt) for op, cnt in op_rows}
    fav_count = int(
        await session.scalar(select(func.count()).select_from(fmodel).where(fmodel.file_id == file_id)) or 0
    )
    recent_rows = (
        await session.execute(
            select(lmodel.actor_name, lmodel.op_type, lmodel.detail, lmodel.created_at)
            .where(lmodel.file_id == file_id)
            .order_by(lmodel.created_at.desc())
            .limit(8)
        )
    ).all()

    doc = RankedDocument(
        id=str(file_id),
        library=library,
        title=meta[0],
        category=meta[1],
        industry=meta[2],
        dept=meta[3],
        file_suffix=meta[4],
        file_size_bytes=meta[5],
        uploader=meta[6],
        uploaded_at=meta[7],
        is_defined=meta[8],
        downloads=counts.get("下载", 0),
        previews=counts.get("预览", 0),
        favorites=fav_count,
    )
    logs = [
        DocumentActivityItem(
            actor_name=str(r[0] or "系统"),
            op_type=str(r[1] or ""),
            detail=str(r[2] or ""),
            created_at=r[3],
        )
        for r in recent_rows
    ]
    return DocumentPeekData(doc=doc, recent_logs=logs)
