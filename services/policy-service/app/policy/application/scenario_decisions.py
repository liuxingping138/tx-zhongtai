"""人对新增场景候选做的决定：采纳、合并、驳回、驳回后改判，以及在来源政策里逐行改场景。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.policy.application import scenario_engine as engine
from app.policy.application import scenario_merging
from app.policy.application.interpretations import to_out as interpretation_out
from app.policy.application.region import make_relation_key
from app.policy.application.scenario_candidates import candidate_out
from app.policy.domain.candidates import (
    KIND_NEW,
    REJECT_REASONS,
    STATUS_ADOPTED,
    STATUS_MERGED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Names,
    ScenarioCandidate,
)
from app.policy.domain.fields import SCENARIO_NAME_FIELDS, SCENARIO_STATE_DUPLICATE
from app.policy.repositories import interpretations as interpretations_repo
from app.policy.repositories import scenario_candidates as repo

NAME_MAX = 255
DUPLICATE_ROW = "这条政策已有同一场景、同一机会类型的解读记录，请改成别的场景或先改另一行"


def _error(message: str, status: int = 422) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=status)


async def _locked(session: AsyncSession, candidate_id: uuid.UUID, version: int) -> ScenarioCandidate:
    candidate = await repo.get_for_update(session, candidate_id)
    if candidate is None:
        raise NotFoundError("新增场景不存在")
    if candidate.version != version:
        raise VersionConflictError()
    return candidate


def _pending(candidate: ScenarioCandidate) -> None:
    if candidate.status != STATUS_PENDING:
        raise ApiError(f"这个场景已经{candidate.status}，刷新后再看", code=ErrorCode.BAD_REQUEST, http_status=409)


def _decided(candidate: ScenarioCandidate, actor: Actor, status: str) -> None:
    now = utcnow()
    candidate.status = status
    candidate.decided_at, candidate.decided_by_id, candidate.decided_by_name = now, actor.id, actor.name
    candidate.version += 1
    candidate.updated_at = now


def _clean_path(names: list[str]) -> Names:
    values = [str(name or "").strip() for name in [*names, "", "", ""][:3]]
    if not values[0]:
        raise _error("要选到至少一级场景")
    if values[2] and not values[1]:
        raise _error("有三级场景却没有二级场景")
    if any(len(name) > NAME_MAX for name in values):
        raise _error(f"场景名称最多 {NAME_MAX} 字")
    return values[0], values[1], values[2]


async def _apply(session: AsyncSession, candidate: ScenarioCandidate, actor: Actor, event: str) -> dict[str, Any]:
    now = utcnow()
    failed = await engine.apply_decision(session, candidate, None, now)
    if failed:
        reasons = "；".join(sorted({reason for _, reason in failed})[:3])
        raise _error(f"有 {len(failed)} 行没法写进行业场景码表：{reasons}")
    await engine.settle(session, [candidate.id])
    await enqueue_event(
        session,
        event_type=event,
        actor=actor,
        target_id=str(candidate.id),
        changes={
            "scenario": " > ".join(name for name in candidate.path() if name),
            "status": candidate.status,
            "target": " > ".join(name for name in candidate.target() if name),
            "adopted_name": candidate.adopted_name,
            "reject_reason": candidate.reject_reason,
        },
    )
    return candidate_out(candidate)


async def adopt(
    session: AsyncSession, actor: Actor, candidate_id: uuid.UUID, *, version: int, name: str
) -> dict[str, Any]:
    """采纳为新场景：写进行业场景码表（按现有规则分配编码），候选下的行回填编码。可以顺手把新的那一级改个说法。"""

    candidate = await _locked(session, candidate_id, version)
    _pending(candidate)
    name = name.strip()
    if candidate.kind == KIND_NEW and name and name != candidate.path()[candidate.new_level - 1]:
        if len(name) > NAME_MAX:
            raise _error(f"场景名称最多 {NAME_MAX} 字")
        candidate.adopted_name = name
    _decided(candidate, actor, STATUS_ADOPTED)
    return await _apply(session, candidate, actor, "policy.scenario_candidate.adopted")


async def merge(
    session: AsyncSession,
    actor: Actor,
    candidate_id: uuid.UUID,
    *,
    version: int,
    target: list[str],
    rename: bool = False,
) -> dict[str, Any]:
    """合并到码表里已有的场景：候选下的行改用那个场景和它的编码，这个说法记成它的别名（以后自动归过去）。

    rename：原场景改用这个新说法（码表和解读里用它的行一起改名，编码不变）。
    """

    candidate = await _locked(session, candidate_id, version)
    _pending(candidate)
    path = _clean_path(target)
    rows = await repo.rows_to_apply(session, candidate.id, "")
    industry = (
        engine.row_names(rows[0])[0] if rows else (candidate.industry_l1, candidate.industry_l2, candidate.industry_l3)
    )
    verdict = (await engine.lookup([(industry, path)])).get((industry, path), {})
    if verdict.get("kind") not in ("exists", "association"):
        raise _error("码表里没有这个场景，合并只能选已有的场景；要新建请用「采纳」")
    if rename:
        named = await scenario_merging.rename_target(
            session, actor, tuple(n for n in path if n), scenario_merging.display_name(candidate)
        )
        padded = [*named, "", "", ""]
        path = (padded[0], padded[1], padded[2])
    candidate.target_l1, candidate.target_l2, candidate.target_l3 = path
    _decided(candidate, actor, STATUS_MERGED)
    return await _apply(session, candidate, actor, "policy.scenario_candidate.merged")


async def reject(
    session: AsyncSession, actor: Actor, candidate_id: uuid.UUID, *, version: int, reason: str, note: str
) -> dict[str, Any]:
    """驳回：行都留着，场景状态标已驳回；以后 AI 再写这个说法自动驳回。"""

    candidate = await _locked(session, candidate_id, version)
    _pending(candidate)
    if reason not in REJECT_REASONS:
        raise _error(f"驳回原因只能是{'、'.join(REJECT_REASONS)}")
    candidate.reject_reason, candidate.note = reason, note.strip()[:2000]
    _decided(candidate, actor, STATUS_REJECTED)
    return await _apply(session, candidate, actor, "policy.scenario_candidate.rejected")


async def reopen(session: AsyncSession, actor: Actor, candidate_id: uuid.UUID, *, version: int) -> dict[str, Any]:
    """驳回的改判回待审。采纳、合并已经写进码表，不在这里撤。"""

    candidate = await _locked(session, candidate_id, version)
    if candidate.status != STATUS_REJECTED:
        raise ApiError("只有已驳回的场景能改判", code=ErrorCode.BAD_REQUEST, http_status=409)
    candidate.reject_reason = candidate.note = ""
    _decided(candidate, actor, STATUS_PENDING)
    candidate.decided_at, candidate.decided_by_id, candidate.decided_by_name = None, "", ""
    return await _apply(session, candidate, actor, "policy.scenario_candidate.reopened")


async def change_row_scenario(
    session: AsyncSession, actor: Actor, row_id: uuid.UUID, *, version: int, names: dict[str, str]
) -> dict[str, Any]:
    """来源政策里逐行改场景：这是人工编辑，更新时间记这个人；改完重新和码表比对、归集。"""

    row = await interpretations_repo.get_for_update(session, row_id)
    if row is None:
        raise NotFoundError("政策解读不存在")
    if row.version != version:
        raise VersionConflictError()
    industry = tuple(str(names.get(field) or "").strip() for field in SCENARIO_NAME_FIELDS[:3])
    scenario = _clean_path([str(names.get(field) or "") for field in SCENARIO_NAME_FIELDS[3:]])
    if not industry[0] or any(len(name) > NAME_MAX for name in industry):
        raise _error("要选到一级行业，行业名称最多 255 字")
    before = engine.row_names(row)
    old_candidate = row.candidate_id
    for field, value in engine.names_payload((industry[0], industry[1], industry[2]), scenario).items():
        setattr(row, field, value)
    key = make_relation_key(row.policy_uid, "", row.opportunity_type, [*industry, *scenario])
    if key != row.relation_key and await interpretations_repo.get_by_relation_key(session, key):
        raise _error(DUPLICATE_ROW, 409)
    row.relation_key = key
    row.industry_code = row.scenario_code = row.industry_scenario_code = ""
    row.scenario_state, row.candidate_id, row.scenario_synced_at = "", None, None
    now = utcnow()
    touched = await engine.classify_rows(session, [row], now)
    if row.scenario_state == SCENARIO_STATE_DUPLICATE:
        raise _error(DUPLICATE_ROW, 409)
    row.updated_at, row.updated_by_id, row.updated_by_name = now, actor.id, actor.name
    await engine.settle(session, {*touched, old_candidate})
    await enqueue_event(
        session,
        event_type="policy.interpretation.scenario_changed",
        actor=actor,
        target_id=str(row.id),
        changes={
            "from": " / ".join(n for n in (*before[0], *before[1]) if n),
            "to": " / ".join(n for n in (*industry, *scenario) if n),
        },
    )
    return interpretation_out(row)
