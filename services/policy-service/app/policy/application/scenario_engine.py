"""新增场景的两步：归集（解读行和码表比对，新的说法归成候选）和套用决定（把候选的决定写到它下面的行上）。

AI 写入、手工新建和编辑、导入、上线补数都走这里。两条约定：
- 系统改的行只加版本号，不动更新时间和操作人：AI 按「更新时间 ≤ 打标时间」认定一行没被人改过，
  重新解读才能替换它、补市场机会才会补它（见 aitag.application.interpreting.untouched）。
- 比对结果写回 AI 自己的标记：码表已有的「是否新增场景」改成否，新增级别写系统算出的一级 / 二级 / 三级 / 新关联。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from platform_common.clock import utcnow
from platform_common.errors import DependencyUnavailableError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.core.database import SessionLocal
from app.policy.application.region import make_relation_key
from app.policy.domain.candidates import (
    KIND_NEW,
    STATUS_ADOPTED,
    STATUS_MERGED,
    STATUS_PENDING,
    Names,
    ScenarioCandidate,
    candidate_key,
    candidate_path,
    level_label,
    renamed_path,
)
from app.policy.domain.fields import (
    SCENARIO_CODE_FIELDS,
    SCENARIO_NAME_FIELDS,
    SCENARIO_STATE_BAD_INDUSTRY,
    SCENARIO_STATE_DUPLICATE,
    SCENARIO_STATE_EXISTS,
    SCENARIO_STATE_INCOMPLETE,
    SCENARIO_STATE_PENDING,
)
from app.policy.domain.models import YES, Interpretation
from app.policy.repositories import interpretations as interpretations_repo
from app.policy.repositories import scenario_candidates as repo

logger = logging.getLogger("policy.scenario_engine")

LOOKUP_CHUNK = 5000
BACKLOG_BATCH = 1000
AUTO_EXISTS_NOTE = "AI 标为新增，码表里已有这个场景，已自动改为已有场景"
DEFAULT_DECIDER = "新增场景审核"
Pair = tuple[Names, Names]


def row_names(row: Interpretation) -> Pair:
    values = [str(getattr(row, field) or "").strip() for field in SCENARIO_NAME_FIELDS]
    return (values[0], values[1], values[2]), (values[3], values[4], values[5])


def names_payload(industry: Names, scenario: Names) -> dict[str, str]:
    return dict(zip(SCENARIO_NAME_FIELDS, (*industry, *scenario), strict=True))


def _set_codes(row: Interpretation, codes: dict[str, Any] | None) -> None:
    for field in SCENARIO_CODE_FIELDS:
        setattr(row, field, str((codes or {}).get(field) or ""))


def _system_touch(row: Interpretation) -> None:
    """系统改了这一行：只加版本号（开着编辑框的人保存时会提示被改过），更新时间和操作人不动。"""

    row.version += 1


async def lookup(pairs: list[Pair]) -> dict[Pair, dict[str, Any]]:
    """一组行业场景名称去码表比对，同样的名称只问一次。"""

    unique = list(dict.fromkeys(pairs))
    out: dict[Pair, dict[str, Any]] = {}
    for start in range(0, len(unique), LOOKUP_CHUNK):
        chunk = unique[start : start + LOOKUP_CHUNK]
        items = [{"key": str(i), **names_payload(*pair)} for i, pair in enumerate(chunk)]
        found = await internal_clients.codebook("POST", "/internal/v1/scenarios/lookup", json={"items": items})
        by_key = {str(item.get("key")): item for item in found}
        out.update({pair: by_key.get(str(i), {}) for i, pair in enumerate(chunk)})
    return out


async def rekey(session: AsyncSession, rows: list[Interpretation]) -> None:
    """按现在的编码、名称重算关联主键。撞上同一政策另一行（同场景、同机会类型）的标「重复」，留着原主键，不删。

    本批行原来的主键也算占用：一行换走的主键不让本批另一行马上接过去，免得按更新顺序撞上唯一约束。
    """

    planned = {
        row.id: make_relation_key(
            row.policy_uid,
            row.industry_scenario_code,
            row.opportunity_type,
            [str(getattr(row, field) or "") for field in SCENARIO_NAME_FIELDS],
        )
        for row in rows
    }
    changing = [key for row in rows if (key := planned[row.id]) != row.relation_key]
    if not changing:
        return
    taken = await repo.taken_relation_keys(session, changing, exclude={row.id for row in rows})
    taken.update(row.relation_key for row in rows)
    for row in rows:
        key = planned[row.id]
        if key == row.relation_key:
            continue
        if key in taken:
            row.scenario_state = SCENARIO_STATE_DUPLICATE
            continue
        taken.add(key)
        row.relation_key = key


def _mark_exists(row: Interpretation, verdict: dict[str, Any]) -> None:
    _set_codes(row, verdict)
    if row.is_new_scenario == YES:
        row.is_new_scenario = "否"
        row.remark = f"{row.remark}；{AUTO_EXISTS_NOTE}" if row.remark else AUTO_EXISTS_NOTE
    row.new_scenario_level = ""
    row.scenario_state = SCENARIO_STATE_EXISTS
    row.candidate_id = None


def _candidate_spec(verdict: dict[str, Any], industry: Names, scenario: Names) -> dict[str, Any]:
    kind = KIND_NEW if verdict.get("kind") == "new" else "新关联"
    level = int(verdict.get("new_level") or 0)
    path = candidate_path(kind, scenario, level)
    spec: dict[str, Any] = {
        "key": candidate_key(kind, industry, scenario, level),
        "kind": kind,
        "new_level": level,
        "level_label": level_label(kind, level),
        "scenario_l1": path[0],
        "scenario_l2": path[1],
        "scenario_l3": path[2],
    }
    if kind != KIND_NEW:
        spec.update(industry_l1=industry[0], industry_l2=industry[1], industry_l3=industry[2])
    return spec


def _sort(
    rows: list[Interpretation], verdicts: dict[Pair, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[Interpretation]], list[Interpretation]]:
    """按比对结果分开：码表已有的直接回填，新的说法按候选归组，其余写明为什么编不了码。"""

    specs: dict[str, dict[str, Any]] = {}
    members: dict[str, list[Interpretation]] = {}
    existing: list[Interpretation] = []
    for row in rows:
        industry, scenario = row_names(row)
        verdict = verdicts.get((industry, scenario), {})
        kind = verdict.get("kind")
        if kind == "exists":
            _mark_exists(row, verdict)
            existing.append(row)
        elif kind in ("new", "association"):
            spec = _candidate_spec(verdict, industry, scenario)
            specs.setdefault(spec["key"], spec)
            members.setdefault(spec["key"], []).append(row)
            row.is_new_scenario, row.new_scenario_level = YES, spec["level_label"]
        else:
            row.scenario_state = SCENARIO_STATE_BAD_INDUSTRY if kind == "bad_industry" else SCENARIO_STATE_INCOMPLETE
    return specs, members, existing


async def _attach(
    session: AsyncSession,
    candidates: dict[str, ScenarioCandidate],
    members: dict[str, list[Interpretation]],
    now: datetime,
) -> set[uuid.UUID]:
    touched: set[uuid.UUID] = set()
    for key, rows_of in members.items():
        candidate = candidates[key]
        touched.add(candidate.id)
        for row in rows_of:
            row.candidate_id, row.scenario_state = candidate.id, SCENARIO_STATE_PENDING
        if candidate.status != STATUS_PENDING:
            for row, reason in await apply_decision(session, candidate, rows_of, now):
                logger.warning("新增场景规则没能套用到解读行 %s：%s", row.id, reason)
    return touched


async def classify_rows(session: AsyncSession, rows: Iterable[Interpretation], now: datetime) -> set[uuid.UUID]:
    """还没比对过的行和码表比对，写场景状态；新的说法归成候选，候选已经决定过的直接套用决定。

    行要已经锁住。返回涉及到的候选，调用方随后 settle 重算它们的统计。
    """

    todo = [row for row in rows if not row.scenario_state]
    for row in todo:
        _system_touch(row)
        if row.industry_scenario_code:  # 导入时带了编码、AI 说已有且查到了编码：认它
            row.scenario_state, row.candidate_id = SCENARIO_STATE_EXISTS, None
    todo = [row for row in todo if not row.industry_scenario_code]
    if not todo:
        return set()
    specs, members, existing = _sort(todo, await lookup([row_names(row) for row in todo]))
    await rekey(session, existing)
    return await _attach(session, await repo.ensure(session, list(specs.values()), now), members, now)


def _final_pair(candidate: ScenarioCandidate, row: Interpretation) -> Pair:
    industry, scenario = row_names(row)
    if candidate.status == STATUS_MERGED:
        return industry, candidate.target()
    if candidate.kind == KIND_NEW and candidate.adopted_name:
        return industry, renamed_path(scenario, candidate.new_level, candidate.adopted_name)
    return industry, scenario


async def _write_to_codebook(candidate: ScenarioCandidate, pairs: list[Pair]) -> dict[Pair, dict[str, Any]]:
    """采纳、合并都经码表的同步接口：已有的返回原编码，新的按规则分配；合并到没挂在这个行业下的场景只新建关联行。"""

    unique = list(dict.fromkeys(pairs))
    items = [
        {"key": str(i), **names_payload(*pair), "source_policy": candidate.sample_title}
        for i, pair in enumerate(unique)
    ]
    found = await internal_clients.codebook(
        "POST",
        "/internal/v1/scenarios/sync",
        json={
            "items": items,
            "caller_name": candidate.decided_by_name or DEFAULT_DECIDER,
            "caller_id": candidate.decided_by_id,
        },
    )
    by_key = {str(item.get("key")): item for item in found}
    return {pair: by_key.get(str(i), {"error": "码表服务没有返回结果"}) for i, pair in enumerate(unique)}


async def apply_decision(
    session: AsyncSession,
    candidate: ScenarioCandidate,
    rows: list[Interpretation] | None,
    now: datetime,
) -> list[tuple[Interpretation, str]]:
    """把候选现在的决定写到它下面的行上（不传 rows 就是全部还没处理的行）。可以反复执行，处理过的行不再动。

    待审、驳回只改场景状态；采纳、合并把名称换成最终的说法、回填编码、重算关联主键。返回没能写进码表的行和原因。
    """

    state = candidate.row_state()
    if rows is None:
        rows = await repo.rows_to_apply(session, candidate.id, state)
    rows = [row for row in rows if row.scenario_state not in (state, SCENARIO_STATE_DUPLICATE)]
    if not rows:
        return []
    if candidate.status not in (STATUS_ADOPTED, STATUS_MERGED):
        for row in rows:
            row.scenario_state = state
            _system_touch(row)
        return []
    finals = {row.id: _final_pair(candidate, row) for row in rows}
    results = await _write_to_codebook(candidate, list(finals.values()))
    failed: list[tuple[Interpretation, str]] = []
    done: list[Interpretation] = []
    for row in rows:
        industry, scenario = finals[row.id]
        result = results[(industry, scenario)]
        if result.get("error") or not result.get("industry_scenario_code"):
            failed.append((row, str(result.get("error") or "码表没有给出编码")))
            continue
        for field, value in names_payload(industry, scenario).items():
            setattr(row, field, value)
        _set_codes(row, result)
        row.scenario_state, row.scenario_synced_at = state, now
        _system_touch(row)
        done.append(row)
    await rekey(session, done)
    return failed


async def recount(session: AsyncSession, candidate_ids: Iterable[uuid.UUID | None]) -> None:
    """重算候选的行数、政策数、主要行业、最近来源。行被删光的候选数到 0，列表里不再出现。"""

    ids = [candidate_id for candidate_id in set(candidate_ids) if candidate_id]
    if not ids:
        return
    await session.flush()
    stats = await repo.stats(session, ids)
    for candidate in await repo.by_ids(session, ids):
        rows, policies, industries, main, last, title = stats.get(candidate.id, (0, 0, 0, "", None, ""))
        candidate.row_count, candidate.policy_count, candidate.industry_count = (
            int(rows),
            int(policies),
            int(industries),
        )
        candidate.main_industry = str(main or "")[:128]
        candidate.sample_title = str(title or candidate.sample_title)[:500]
        if last is not None and last > candidate.last_seen_at:
            candidate.last_seen_at = last


async def refresh_similar(candidates: list[ScenarioCandidate]) -> None:
    """新候选算一次码表里最像的已有场景，列表的「码表相似」「最像的已有场景」两列读它。取不到下次再算。"""

    todo = [candidate for candidate in candidates if not candidate.similar_level]
    if not todo:
        return
    items = [
        {
            "key": str(candidate.id),
            "path": [name for name in candidate.path() if name],
            "industry_l1": [candidate.main_industry],
        }
        for candidate in todo
    ]
    try:
        found = await internal_clients.codebook("POST", "/internal/v1/scenarios/context", json={"items": items})
    except DependencyUnavailableError:
        logger.warning("码表服务暂时取不到相似场景，%s 个新候选下次再算", len(todo))
        return
    by_key = {str(item.get("key")): item for item in found}
    for candidate in todo:
        context = by_key.get(str(candidate.id)) or {}
        similar = context.get("similar") or []
        best = similar[0] if similar else {}
        candidate.similar_name = " > ".join(best.get("path") or [])[:800]
        candidate.similar_score = float(best.get("score") or 0.0)
        candidate.similar_level = str(context.get("best_level") or "无")


async def settle(session: AsyncSession, candidate_ids: Iterable[uuid.UUID | None]) -> None:
    """归集、决定之后收尾：重算涉及到的候选，新候选补上相似场景。"""

    ids = [candidate_id for candidate_id in set(candidate_ids) if candidate_id]
    await recount(session, ids)
    await refresh_similar(await repo.by_ids(session, ids))


async def refresh_pending_similar() -> int:
    """待审候选重算一遍「最像的已有场景」：相似度的口径改了、码表里加了一批场景之后跑。"""

    async with SessionLocal() as session:
        candidates = await repo.pending(session)
        for candidate in candidates:
            candidate.similar_level = ""
        await refresh_similar(candidates)
        await session.commit()
    return len(candidates)


async def classify_quietly(
    session: AsyncSession, rows: Iterable[Interpretation], also: Iterable[uuid.UUID | None] = ()
) -> None:
    """新建、编辑、导入顺手比对：码表服务连不上不耽误保存，行留着「还没比对」，下次补比对时接上。"""

    try:
        touched = await classify_rows(session, rows, utcnow())
    except DependencyUnavailableError:
        logger.warning("码表服务暂时连不上，解读行先不比对，下次补")
        await recount(session, also)
        return
    await settle(session, {*touched, *also})


async def classify_backlog(max_rows: int | None = None) -> int:
    """把还没比对过的行一批批比对完（AI 每批写完、上线补数时跑）。码表服务连不上就停，下次接着比。"""

    done = 0
    while max_rows is None or done < max_rows:
        async with SessionLocal() as session:
            rows = await interpretations_repo.unclassified_rows(session, BACKLOG_BATCH)
            if not rows:
                break
            try:
                touched = await classify_rows(session, rows, utcnow())
                await settle(session, touched)
            except DependencyUnavailableError:
                logger.warning("码表服务暂时连不上，还有解读行没和码表比对，下次接着比")
                await session.rollback()
                break
            await session.commit()
            done += len(rows)
    return done
