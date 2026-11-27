"""智库统计基础仓储：资产体量、分类分布、中标转化、行为汇总与时间趋势聚合。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile, KnowledgeOpLog
from app.library.domain.models import (
    ProposalFavorite,
    ProposalFile,
    ProposalOpLog,
    ReportFavorite,
    ReportFile,
    ReportOpLog,
)
from app.statistics.domain.specs import (
    ALL_LIBRARIES,
    Granularity,
    LibraryKey,
    format_bucket_label,
    parse_wan_amount,
)


@dataclass(frozen=True)
class LibraryAssetSummary:
    library: LibraryKey
    files: int
    defined: int
    size_bytes: int


@dataclass(frozen=True)
class BehaviorSummary:
    uploads: int
    previews: int
    downloads: int
    favorites: int
    unfavorites: int
    governance: int
    active_users: int


@dataclass(frozen=True)
class ProposalWinSummary:
    total: int
    won: int
    lost: int
    pending: int
    aborted: int
    win_rate: float
    win_amount_wan: float


@dataclass(frozen=True)
class TrendBucket:
    bucket_key: str
    label: str
    knowledge_uploads: int
    reports_uploads: int
    proposals_uploads: int
    governance: int
    previews: int
    downloads: int
    active_users: int


FILE_MODELS: dict[LibraryKey, type[Any]] = {
    "knowledge": KnowledgeFile,
    "reports": ReportFile,
    "proposals": ProposalFile,
}
LOG_MODELS: dict[LibraryKey, type[Any]] = {
    "knowledge": KnowledgeOpLog,
    "reports": ReportOpLog,
    "proposals": ProposalOpLog,
}
FAV_MODELS: dict[LibraryKey, type[Any]] = {
    "knowledge": KnowledgeFavorite,
    "reports": ReportFavorite,
    "proposals": ProposalFavorite,
}


def file_columns_map(lib: LibraryKey) -> dict[str, Any]:
    if lib == "knowledge":
        return {
            "title": KnowledgeFile.file_name,
            "file_type": KnowledgeFile.file_type,
            "industry": KnowledgeFile.industry_type,
            "operator": KnowledgeFile.operator_type,
            "market": KnowledgeFile.market_category,
            "province": KnowledgeFile.prov_name,
            "region": KnowledgeFile.prov_name,
            "dept": KnowledgeFile.depart_affiliation,
            "category": KnowledgeFile.file_type,
        }
    if lib == "reports":
        return {
            "title": ReportFile.report_name,
            "file_type": ReportFile.report_type,
            "report_type": ReportFile.report_type,
            "industry": ReportFile.industry_tags,
            "delivery_dept": ReportFile.delivery_dept,
            "dept": ReportFile.delivery_dept,
            "region": ReportFile.region_tag,
            "temp_support": ReportFile.is_temp_support,
            "category": ReportFile.report_type,
        }
    return {
        "title": ProposalFile.proposal_name,
        "file_type": ProposalFile.proposal_type,
        "proposal_type": ProposalFile.proposal_type,
        "win_result": ProposalFile.result_status,
        "industry": ProposalFile.industry_tags,
        "owner_dept": ProposalFile.owner_dept,
        "dept": ProposalFile.owner_dept,
        "region": ProposalFile.region_tag,
        "opportunity_source": ProposalFile.opportunity_source,
        "category": ProposalFile.proposal_type,
    }


def logs_union_subquery(
    libraries: tuple[LibraryKey, ...],
    start_utc: datetime | None,
    end_utc: datetime,
) -> Any:
    parts = []
    for lib in libraries:
        model = LOG_MODELS[lib]
        stmt = select(
            literal(lib).label("library"),
            model.file_id.label("file_id"),
            model.actor_id.label("actor_id"),
            model.actor_name.label("actor_name"),
            model.op_type.label("op_type"),
            model.created_at.label("created_at"),
        ).where(model.created_at < end_utc)
        if start_utc is not None:
            stmt = stmt.where(model.created_at >= start_utc)
        parts.append(stmt)
    return union_all(*parts).subquery("tt_logs")


async def fetch_library_totals(session: AsyncSession) -> dict[LibraryKey, LibraryAssetSummary]:
    result: dict[LibraryKey, LibraryAssetSummary] = {}
    for lib in ALL_LIBRARIES:
        model = FILE_MODELS[lib]
        stmt = select(
            func.count(model.id),
            func.coalesce(func.sum(case((model.is_defined.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(model.file_size_bytes), 0),
        )
        row = (await session.execute(stmt)).one()
        result[lib] = LibraryAssetSummary(
            library=lib,
            files=int(row[0] or 0),
            defined=int(row[1] or 0),
            size_bytes=int(row[2] or 0),
        )
    return result


async def fetch_behavior_summary(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    start_utc: datetime | None,
    end_utc: datetime,
) -> BehaviorSummary:
    logs = logs_union_subquery(libraries, start_utc, end_utc)
    op_rows = (await session.execute(select(logs.c.op_type, func.count()).group_by(logs.c.op_type))).all()
    counts: dict[str, int] = {str(op): int(cnt) for op, cnt in op_rows}
    active = int(await session.scalar(select(func.count(func.distinct(logs.c.actor_id)))) or 0)
    return BehaviorSummary(
        uploads=counts.get("上传", 0),
        previews=counts.get("预览", 0),
        downloads=counts.get("下载", 0),
        favorites=counts.get("收藏", 0),
        unfavorites=counts.get("取消收藏", 0),
        governance=counts.get("上传标签", 0) + counts.get("编辑", 0),
        active_users=active,
    )


async def fetch_dimension_raw_counts(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    dimension_key: str,
) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for lib in libraries:
        col = file_columns_map(lib).get(dimension_key)
        if col is None:
            continue
        stmt = select(col, func.count()).group_by(col)
        for val, cnt in (await session.execute(stmt)).all():
            rows.append((str(val or ""), int(cnt)))
    return rows


async def fetch_proposal_win_summary(session: AsyncSession) -> ProposalWinSummary:
    rows = (await session.execute(select(ProposalFile.result_status, ProposalFile.win_amount))).all()
    total = len(rows)
    won = lost = pending = aborted = 0
    win_amount = 0.0
    for status, amount_text in rows:
        s = (status or "").strip()
        if s == "中标":
            won += 1
            win_amount += parse_wan_amount(amount_text)
        elif s == "未中标":
            lost += 1
        elif s == "流标":
            aborted += 1
        else:
            pending += 1
    decided = won + lost
    win_rate = round((won * 100.0) / decided, 1) if decided > 0 else 0.0
    return ProposalWinSummary(
        total=total,
        won=won,
        lost=lost,
        pending=pending,
        aborted=aborted,
        win_rate=win_rate,
        win_amount_wan=round(win_amount, 2),
    )


async def fetch_trend_series(
    session: AsyncSession,
    *,
    libraries: tuple[LibraryKey, ...],
    start_utc: datetime | None,
    end_utc: datetime,
    granularity: Granularity,
) -> list[TrendBucket]:
    logs = logs_union_subquery(libraries, start_utc, end_utc)
    bj_ts = func.timezone("Asia/Shanghai", logs.c.created_at)
    bucket_col = func.date_trunc(granularity, bj_ts).label("bucket")

    op_stmt = (
        select(bucket_col, logs.c.library, logs.c.op_type, func.count())
        .group_by(bucket_col, logs.c.library, logs.c.op_type)
        .order_by(bucket_col)
    )
    active_stmt = (
        select(bucket_col, func.count(func.distinct(logs.c.actor_id))).group_by(bucket_col).order_by(bucket_col)
    )

    acc: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for bkt, lib, op_type, cnt in (await session.execute(op_stmt)).all():
        n = int(cnt)
        if op_type == "上传":
            acc[bkt][f"{lib}_uploads"] += n
        elif op_type in {"上传标签", "编辑"}:
            acc[bkt]["governance"] += n
        elif op_type == "预览":
            acc[bkt]["previews"] += n
        elif op_type == "下载":
            acc[bkt]["downloads"] += n

    for bkt, active_cnt in (await session.execute(active_stmt)).all():
        acc[bkt]["active_users"] = int(active_cnt)

    return [
        TrendBucket(
            bucket_key=bkt.strftime("%Y-%m-%d"),
            label=format_bucket_label(bkt, granularity),
            knowledge_uploads=acc[bkt]["knowledge_uploads"],
            reports_uploads=acc[bkt]["reports_uploads"],
            proposals_uploads=acc[bkt]["proposals_uploads"],
            governance=acc[bkt]["governance"],
            previews=acc[bkt]["previews"],
            downloads=acc[bkt]["downloads"],
            active_users=acc[bkt]["active_users"],
        )
        for bkt in sorted(acc.keys())
    ]
