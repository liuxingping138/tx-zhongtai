"""新增场景审核页的查询：候选列表（页签数和一句话结论）、单个候选的详情、码表上下文和来源解读行。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from platform_common.clock import BEIJING, format_beijing, utcnow
from platform_common.errors import DependencyUnavailableError, NotFoundError
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.policy.domain.candidates import (
    KIND_NEW,
    LEVEL_CHOICES,
    REJECT_REASONS,
    STATUS_CHOICES,
    ScenarioCandidate,
)
from app.policy.domain.models import Interpretation
from app.policy.repositories import scenario_candidates as repo

logger = logging.getLogger("policy.scenario_candidates")

SIMILAR_LEVELS = ("高", "中", "无")
REASON_LIMIT = 3
DEEPEST = 3  # 场景最多三级：新的是三级时没有下级
# AI 理由取自解读行的备注；这几句是系统追加的说明，不算理由
SYSTEM_NOTES = ("AI 标为已有场景", "AI 标为新增，码表里已有")


def _path_text(names: tuple[str, ...]) -> str:
    return " > ".join(name for name in names if name)


def candidate_out(row: ScenarioCandidate) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "new_level": row.new_level,
        "level_label": row.level_label,
        "name": row.path()[row.new_level - 1] if row.kind == KIND_NEW else _path_text(row.path()),
        "scenario_l1": row.scenario_l1,
        "scenario_l2": row.scenario_l2,
        "scenario_l3": row.scenario_l3,
        "parent": _path_text(row.path()[: row.new_level - 1]) if row.kind == KIND_NEW else "",
        "industry": "/".join(name for name in (row.industry_l1, row.industry_l2, row.industry_l3) if name),
        "status": row.status,
        "adopted_name": row.adopted_name,
        "target": _path_text(row.target()),
        "target_l1": row.target_l1,
        "target_l2": row.target_l2,
        "target_l3": row.target_l3,
        "reject_reason": row.reject_reason,
        "note": row.note,
        "decided_at": format_beijing(row.decided_at),
        "decided_by_name": row.decided_by_name,
        "row_count": row.row_count,
        "policy_count": row.policy_count,
        "industry_count": row.industry_count,
        "main_industry": row.main_industry,
        "sample_title": row.sample_title,
        "similar_name": row.similar_name,
        "similar_score": row.similar_score,
        "similar_level": row.similar_level,
        "first_seen_at": format_beijing(row.first_seen_at),
        "last_seen_at": format_beijing(row.last_seen_at),
        "version": row.version,
    }


def _today(now: datetime) -> datetime:
    return now.astimezone(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)


async def list_candidates(session: AsyncSession, filters: Filters, *, page: int, page_size: int) -> dict[str, Any]:
    items, total = await repo.list_items(session, filters=filters, page=page, page_size=page_size)
    return {
        "items": [candidate_out(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": await repo.summary(session, _today(utcnow())),
    }


async def candidate_options() -> dict[str, Any]:
    try:
        industries, _ = await internal_clients.scenario_l1_names()
    except DependencyUnavailableError:
        logger.warning("行业场景码表暂时取不到，新增场景的一级行业筛选先不给候选值")
        industries = []
    fixed = {
        "status": STATUS_CHOICES,
        "industry_l1": tuple(dict.fromkeys(industries)),
        "level_label": LEVEL_CHOICES,
        "similar_level": SIMILAR_LEVELS,
    }
    return {
        "options": {field: {"items": list(items), "truncated": False} for field, items in fixed.items()},
        "reject_reasons": list(REJECT_REASONS),
    }


async def _get(session: AsyncSession, candidate_id: uuid.UUID) -> ScenarioCandidate:
    candidate = await repo.get(session, candidate_id)
    if candidate is None:
        raise NotFoundError("新增场景不存在")
    return candidate


def _reasons(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    out = []
    for remark, count in rows:
        text = str(remark or "").strip()
        if not text or text.startswith(SYSTEM_NOTES):
            continue
        out.append({"text": text[:300], "count": int(count)})
        if len(out) >= REASON_LIMIT:
            break
    return out


async def candidate_detail(session: AsyncSession, candidate_id: uuid.UUID) -> dict[str, Any]:
    """详情：候选本身，加上各行业几行、下级新场景各几行、AI 给的理由里最常见的几条。"""

    candidate = await _get(session, candidate_id)
    industries = await repo.breakdown(
        session, candidate.id, Interpretation.industry_l1, Interpretation.industry_l2, Interpretation.industry_l3
    )
    children: list[dict[str, Any]] = []
    if candidate.kind == KIND_NEW and candidate.new_level < DEEPEST:
        deeper = (Interpretation.scenario_l2_name, Interpretation.scenario_l3_name)[candidate.new_level - 1 :]
        for row in await repo.breakdown(session, candidate.id, *deeper):
            names, count = row[:-1], row[-1]
            if any(names):
                children.append({"path": _path_text(tuple(str(name) for name in names)), "rows": int(count)})
    reasons = _reasons(await repo.breakdown(session, candidate.id, Interpretation.remark))
    return {
        **candidate_out(candidate),
        "industries": [{"path": "/".join(name for name in row[:3] if name), "rows": int(row[3])} for row in industries],
        "children": children,
        "reasons": reasons,
    }


async def candidate_context(session: AsyncSession, candidate_id: uuid.UUID) -> dict[str, Any]:
    """码表上下文：要挂的位置下已有哪些场景、码表里最像的已有场景、这个场景已挂在哪些行业下。现取，不缓存。"""

    candidate = await _get(session, candidate_id)
    industries = [str(row[0]) for row in await repo.breakdown(session, candidate.id, Interpretation.industry_l1)]
    item = {"key": str(candidate.id), "path": [name for name in candidate.path() if name], "industry_l1": industries}
    found = await internal_clients.codebook("POST", "/internal/v1/scenarios/context", json={"items": [item]})
    context = found[0] if found else {}
    return {
        "siblings": context.get("siblings") or [],
        "similar": context.get("similar") or [],
        "industries": context.get("industries") or [],
    }


def _row_out(row: Interpretation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "policy_title": row.policy_title,
        "created_at": format_beijing(row.created_at),
        "industry": "/".join(name for name in (row.industry_l1, row.industry_l2, row.industry_l3) if name),
        "industry_l1": row.industry_l1,
        "industry_l2": row.industry_l2,
        "industry_l3": row.industry_l3,
        "scenario_l1_name": row.scenario_l1_name,
        "scenario_l2_name": row.scenario_l2_name,
        "scenario_l3_name": row.scenario_l3_name,
        "opportunity_type": row.opportunity_type,
        "remark": row.remark,
        "scenario_state": row.scenario_state,
        "version": row.version,
    }


async def candidate_rows(
    session: AsyncSession, candidate_id: uuid.UUID, *, keyword: str | None, page: int, page_size: int
) -> dict[str, Any]:
    candidate = await _get(session, candidate_id)
    rows, total = await repo.rows_page(
        session, candidate.id, keyword=(keyword or "").strip() or None, page=page, page_size=page_size
    )
    return {"items": [_row_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}
