"""新增场景补描述：采纳进码表的新场景只有名称，政策服务的打标任务「新增场景补描述」让 AI 写描述（待补充 → 待确认），
业务人员在新增场景审核里核对、改好后确认（已确认）。同一场景路径在各行业、各客群下的行一起改。"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.fields import ENRICH_DONE, ENRICH_PENDING, ENRICH_REVIEW
from app.domain.models import Scenario
from app.domain.scenario_similarity import ScenarioNodes
from app.repositories import code_tables as repo

DESC_FIELDS = ("desc_90", "desc_130", "desc_pest")
EXAMPLES = 3
TEXT_MAX = 4000
AI_ACTOR = Actor(id="policy-ai-tagging", name="政策AI打标")


def _path(raw: Any) -> tuple[str, ...]:
    return tuple(str(name or "").strip() for name in (raw or []) if str(name or "").strip())


def _row_path(row: Scenario) -> tuple[str, ...]:
    """从一级开始取连续非空的场景层级：空缺或全空的不拼成错位路径。"""

    out: list[str] = []
    for name in (row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name):
        cleaned = str(name or "").strip()
        if not cleaned:
            break
        out.append(cleaned)
    return tuple(out)


def _level_desc(row: Scenario, level: int) -> str:
    if level not in (1, 2, 3):
        return ""
    return str(getattr(row, f"scenario_l{level}_desc") or "")


def _group(rows: list[Scenario]) -> dict[tuple[str, ...], list[Scenario]]:
    grouped: dict[tuple[str, ...], list[Scenario]] = {}
    for row in rows:
        path = _row_path(row)
        if not path:
            continue
        grouped.setdefault(path, []).append(row)
    return grouped


def _node_out(path: tuple[str, ...], rows: list[Scenario]) -> dict[str, Any]:
    first = rows[0]
    return {
        "key": " > ".join(path),
        "path": list(path),
        "level": len(path),
        "industries": sorted({"/".join(n for n in (r.industry_l1, r.industry_l2, r.industry_l3) if n) for r in rows}),
        "rows": len(rows),
        "source_policy": next((r.source_policy for r in rows if r.source_policy), ""),
        "desc_90": first.desc_90,
        "desc_130": first.desc_130,
        "desc_pest": first.desc_pest,
        "level_desc": _level_desc(first, len(path)),
        "updated_at": first.updated_at.isoformat() if first.updated_at else "",
    }


async def backlog(session: AsyncSession, limit: int) -> list[dict[str, Any]]:
    """待补充的场景（按场景路径合并），带上写描述要参照的：上级场景的描述、同级几个已有场景的名称和描述。"""

    grouped = _group(await repo.rows_with_enrich(session, ENRICH_PENDING, lock=False))
    nodes = ScenarioNodes.from_rows(await repo.scenario_nodes(session))
    out = []
    for path, rows in list(grouped.items())[:limit]:
        item = _node_out(path, rows)
        parent = path[:-1]
        item["parent_desc"] = nodes.nodes[parent].desc if parent in nodes.nodes else ""
        siblings = [s["name"] for s in nodes.siblings(path, {r.industry_l1 for r in rows}) if s["name"] != path[-1]]
        item["examples"] = [
            {"name": name, "desc": nodes.nodes[(*parent, name)].desc[:200]}
            for name in siblings
            if (*parent, name) in nodes.nodes and nodes.nodes[(*parent, name)].desc
        ][:EXAMPLES]
        out.append(item)
    return out


async def count(session: AsyncSession, status: str) -> int:
    return len(_group(await repo.rows_with_enrich(session, status, lock=False)))


def _apply(rows: list[Scenario], path: tuple[str, ...], values: dict[str, Any], actor: Actor, status: str) -> None:
    level, now = len(path), utcnow()
    seen_hashes: set[str] = set()
    for row in rows:
        for field in DESC_FIELDS:
            if values.get(field) is not None:
                setattr(row, field, str(values[field]).strip()[:TEXT_MAX])
        if values.get("level_desc") is not None and level in (1, 2, 3):
            setattr(row, f"scenario_l{level}_desc", str(values["level_desc"]).strip()[:TEXT_MAX])
        if not row.scenario_tag:
            row.scenario_tag = path[-1]
        if not row.scenario_level:
            row.scenario_level = str(level)
        row.enrich_status = status
        row.refresh_hash()
        digest = getattr(row, "content_hash", None)
        if digest:
            if digest in seen_hashes:
                raise ApiError(
                    "补充描述后有两条场景记录完全相同，请先清理重复行",
                    code=ErrorCode.DUPLICATE,
                    http_status=409,
                )
            seen_hashes.add(digest)
        row.version += 1
        row.updated_at, row.updated_by_id, row.updated_by_name = now, actor.id, actor.name


async def write(session: AsyncSession, items: list[dict[str, Any]]) -> dict[str, int]:
    """AI 写好的描述写进去，改成待确认。AI 没写出来的（失败）也改成待确认，描述空着让人补，免得天天重问。"""

    updated = 0
    for item in items:
        path = _path(item.get("path"))
        if not path:
            continue
        rows = await repo.rows_with_enrich(session, ENRICH_PENDING, lock=True, path=path)
        _apply(rows, path, item, AI_ACTOR, ENRICH_REVIEW)
        updated += len(rows)
    await session.flush()
    return {"updated": updated}


async def pending_review(session: AsyncSession) -> list[dict[str, Any]]:
    """待确认的场景（按场景路径合并），新增场景审核的「补充待确认」页签用。"""

    grouped = _group(await repo.rows_with_enrich(session, ENRICH_REVIEW, lock=False))
    return [_node_out(path, rows) for path, rows in grouped.items()]


async def confirm(session: AsyncSession, actor: Actor, raw_path: list[str], values: dict[str, Any]) -> dict[str, Any]:
    """人核对过（可改）后确认：这个场景各行业、各客群的行一起写上，改成已确认。"""

    path = _path(raw_path)
    rows = await repo.rows_with_enrich(session, ENRICH_REVIEW, lock=True, path=path) if path else []
    if not rows:
        raise ApiError("这个场景不在待确认里了，刷新后再看", code=ErrorCode.BAD_REQUEST, http_status=409)
    _apply(rows, path, values, actor, ENRICH_DONE)
    await session.flush()
    await enqueue_event(
        session,
        event_type="codebook.scenario.enrich_confirmed",
        actor=actor,
        extra={"path": " > ".join(path), "rows": len(rows)},
    )
    return {"rows": len(rows)}
