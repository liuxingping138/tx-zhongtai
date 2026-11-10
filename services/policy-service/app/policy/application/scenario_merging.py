"""新增场景之间、新增场景和已有场景之间的合并：

- 两个待审场景其实是同一个（「机场建设数字化管理」和「智慧机场工程建设管理」）：把一个并进另一个，行搬过去，
  以后 AI 再写被并入的说法也归到这里（候选的 merged_into，scenario_engine 归集时顺着找）。
- 合并到已有场景时让原场景改用新说法：码表里那个场景各行业、各客群的行和解读行一起改名，编码不变。
"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.similarity import MEDIUM, similarity, similarity_level
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.policy.application import scenario_engine as engine
from app.policy.application.scenario_candidates import candidate_out
from app.policy.domain.candidates import KIND_NEW, STATUS_MERGED, STATUS_PENDING, ScenarioCandidate, candidate_key
from app.policy.repositories import scenario_candidates as repo

PEER_LIMIT = 5


def display_name(candidate: ScenarioCandidate) -> str:
    path = candidate.path()
    return path[candidate.new_level - 1] if candidate.kind == KIND_NEW and candidate.new_level else path[-1]


async def peers(session: AsyncSession, candidate_id: uuid.UUID) -> list[dict[str, Any]]:
    """别的待审场景里名称和它相似的（同一个场景换了说法），最像的在前。"""

    candidate = await repo.get(session, candidate_id)
    if candidate is None:
        raise NotFoundError("新增场景不存在")
    name = display_name(candidate)
    scored = [
        (similarity(name, display_name(other)), other) for other in await repo.pending_others(session, candidate.id)
    ]
    best = sorted((item for item in scored if item[0] >= MEDIUM), key=lambda item: (-item[0], -item[1].policy_count))
    return [
        {**candidate_out(other), "score": score, "level": similarity_level(score)} for score, other in best[:PEER_LIMIT]
    ]


async def _locked(session: AsyncSession, candidate_id: uuid.UUID, version: int) -> ScenarioCandidate:
    candidate = await repo.get_for_update(session, candidate_id)
    if candidate is None:
        raise NotFoundError("新增场景不存在")
    if candidate.version != version:
        raise VersionConflictError()
    if candidate.status != STATUS_PENDING:
        raise ApiError(
            f"「{display_name(candidate)}」已经{candidate.status}，刷新后再看",
            code=ErrorCode.BAD_REQUEST,
            http_status=409,
        )
    return candidate


async def absorb(
    session: AsyncSession,
    actor: Actor,
    candidate_id: uuid.UUID,
    *,
    version: int,
    peer_id: uuid.UUID,
    peer_version: int,
) -> dict[str, Any]:
    """把另一个待审场景并进这个：它的行改成这个场景的说法、搬过来，以后那个说法也归到这里。"""

    if peer_id == candidate_id:
        raise ApiError("不能并入自己", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    target = await _locked(session, candidate_id, version)
    peer = await _locked(session, peer_id, peer_version)
    if (peer.kind, peer.new_level) != (target.kind, target.new_level):
        raise ApiError(
            f"两个场景的新增级别不同（{peer.level_label}、{target.level_label}），不能合成一个，请分别决定",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    now = utcnow()
    rows = await repo.rows_of(session, peer.id)
    engine.move_rows(rows, peer, target)
    for row in rows:
        row.scenario_state = target.row_state()
        row.version += 1
    await engine.rekey(session, rows)
    peer.status, peer.merged_into = STATUS_MERGED, target.id
    peer.target_l1, peer.target_l2, peer.target_l3 = target.path()
    peer.decided_at, peer.decided_by_id, peer.decided_by_name = now, actor.id, actor.name
    peer.version += 1
    peer.updated_at = now
    target.version += 1
    target.updated_at = now
    await engine.settle(session, [target.id, peer.id])
    await enqueue_event(
        session,
        event_type="policy.scenario_candidate.absorbed",
        actor=actor,
        target_id=str(target.id),
        changes={"from": display_name(peer), "into": display_name(target), "rows": len(rows)},
    )
    return candidate_out(target)


async def rename_impact(session: AsyncSession, target: tuple[str, ...]) -> dict[str, int]:
    """合并时让原场景改用新说法，会改多少行：码表里这个场景的行（各行业、各客群）、解读里用这个场景的行。"""

    if not target:
        raise ApiError("请选择目标场景", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    preview = await internal_clients.codebook(
        "POST", "/internal/v1/scenarios/rename", json={"path": list(target), "new_name": target[-1], "dry_run": True}
    )
    return {
        "codebook_rows": int(preview.get("rows") or 0),
        "interpretation_rows": await repo.count_rows_with_prefix(session, target),
    }


async def rename_target(
    session: AsyncSession,
    actor: Actor,
    target: tuple[str, ...],
    new_name: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> tuple[str, ...]:
    """把已有场景改名：先改码表（同一上级下已有这个名字会被拒绝），再改解读行和挂在它下面的待审场景。返回改名后的路径。"""

    renamed = (*target[:-1], new_name)
    if new_name == target[-1]:
        return target
    await internal_clients.codebook(
        "POST",
        "/internal/v1/scenarios/rename",
        json={"path": list(target), "new_name": new_name, "caller_name": actor.name, "caller_id": actor.id},
    )
    await repo.rename_rows(session, target, new_name)
    level = len(target)
    # 解读行改了名，没编码的行关联主键里带着名称，要重算
    await engine.rekey(session, await repo.codeless_rows_with_prefix(session, renamed))
    assigned: set[str] = set()
    for candidate in await repo.candidates_with_prefix(session, target):
        if exclude_id is not None and candidate.id == exclude_id:
            continue
        setattr(candidate, f"scenario_l{level}", new_name)
        key = candidate_key(
            candidate.kind,
            (candidate.industry_l1, candidate.industry_l2, candidate.industry_l3),
            candidate.path(),
            candidate.new_level,
        )
        # 规则跟着改名，以后 AI 按新名称写的也归到它；新名称的规则已经有了就留着旧的
        if key != candidate.key and key not in assigned and not await repo.key_taken(session, key):
            candidate.key = key
            assigned.add(key)
    return renamed
