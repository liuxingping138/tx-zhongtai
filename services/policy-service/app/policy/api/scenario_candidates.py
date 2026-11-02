"""新增场景审核：AI 解读出的新场景按场景归成候选，人在这里采纳、合并或驳回。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session
from app.policy.api.schemas import (
    CandidateAbsorbRequest,
    CandidateAdoptRequest,
    CandidateBatchMerge,
    CandidateBatchReject,
    CandidateMergeRequest,
    CandidateRejectRequest,
    CandidateVersion,
)
from app.policy.application import scenario_batch as batch
from app.policy.application import scenario_candidates as service
from app.policy.application import scenario_decisions as decisions
from app.policy.application import scenario_merging as merging

router = APIRouter(prefix="/api/v1/policy/scenario-candidates", tags=["policy-scenario-candidates"])
RESOURCE = "policy.scenario_candidates"
# 采纳、合并往行业场景码表里写：还要码表可管理，没有码表编辑权的人不能借这里往码表加行。
CODEBOOK = ("codebook.scenarios", "update")


def candidate_filters(
    status: list[str] | None = Query(default=None, description="待审、已采纳、已合并、已驳回"),
    keyword: list[str] | None = Query(default=None, description="场景名称关键词"),
    industry_l1: list[str] | None = Query(default=None),
    level_label: list[str] | None = Query(default=None),
    similar_level: list[str] | None = Query(default=None),
    match: list[str] | None = Query(
        default=None, description="码表里像它的：AI 建议合并、名称很像、名称有点像、没有像的"
    ),
    min_policies: int | None = Query(default=None, ge=1, le=100000),
) -> Filters:
    return {
        "status": status,
        "keyword": keyword,
        "industry_l1": industry_l1,
        "level_label": level_label,
        "similar_level": similar_level,
        "match": match,
        "min_policies": min_policies,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(candidate_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """按政策数从多到少；带各状态的数和一句话结论用的汇总。"""

    try:
        return success_json(await service.list_candidates(session, filters, page=page, page_size=page_size))
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_options(
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.candidate_options())


@router.get("/pending-count")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def pending_count(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """侧栏「新增场景审核」旁的待审数。"""

    return success_json({"pending": await service.pending_count(session)})


@router.post("/batch-reject")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def batch_reject(
    body: CandidateBatchReject,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
) -> JSONResponse:
    """勾选的几个一起驳回；被人改过、已经决定过的跳过并写明原因。"""

    items = [(item.id, item.version) for item in body.items]
    return success_json(await batch.batch_reject(session, actor, items, reason=body.reason, note=body.note))


@router.post("/batch-merge")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def batch_merge(
    body: CandidateBatchMerge,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
    _codebook: Actor = Depends(require_policy_permission(*CODEBOOK)),
) -> JSONResponse:
    """勾选的几个一起合并到同一个已有场景。"""

    items = [(item.id, item.version) for item in body.items]
    return success_json(await batch.batch_merge(session, actor, items, target=body.target))


@router.get("/{candidate_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    candidate_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.candidate_detail(session, candidate_id))


@router.get("/{candidate_id}/context")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_context(
    candidate_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """码表里同一上级下已有的场景、字面最像的已有场景。"""

    return success_json(await service.candidate_context(session, candidate_id))


@router.get("/{candidate_id}/rows")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_rows(
    candidate_id: uuid.UUID,
    keyword: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """提出这个场景的解读行（来源政策），最近的在前。"""

    return success_json(
        await service.candidate_rows(session, candidate_id, keyword=keyword, page=page, page_size=page_size)
    )


@router.get("/{candidate_id}/peers")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_peers(
    candidate_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """别的待审场景里名称和它相似的（可能是同一个场景换了说法）。"""

    return success_json({"items": await merging.peers(session, candidate_id)})


@router.get("/{candidate_id}/rename-impact")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_rename_impact(
    candidate_id: uuid.UUID,
    target: list[str] = Query(..., min_length=1, max_length=3),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """合并时让原场景改用新说法会改多少行。"""

    path = tuple(name.strip() for name in target if name.strip())
    return success_json(await merging.rename_impact(session, path))


@router.post("/{candidate_id}/absorb")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def absorb(
    candidate_id: uuid.UUID,
    body: CandidateAbsorbRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
) -> JSONResponse:
    """把另一个相似的待审场景并进这个。"""

    return success_json(
        await merging.absorb(
            session, actor, candidate_id, version=body.version, peer_id=body.peer_id, peer_version=body.peer_version
        )
    )


@router.post("/{candidate_id}/adopt")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def adopt(
    candidate_id: uuid.UUID,
    body: CandidateAdoptRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
    _codebook: Actor = Depends(require_policy_permission(*CODEBOOK)),
) -> JSONResponse:
    return success_json(await decisions.adopt(session, actor, candidate_id, version=body.version, name=body.name))


@router.post("/{candidate_id}/merge")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def merge(
    candidate_id: uuid.UUID,
    body: CandidateMergeRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
    _codebook: Actor = Depends(require_policy_permission(*CODEBOOK)),
) -> JSONResponse:
    return success_json(
        await decisions.merge(
            session, actor, candidate_id, version=body.version, target=body.target, rename=body.rename
        )
    )


@router.post("/{candidate_id}/reject")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def reject(
    candidate_id: uuid.UUID,
    body: CandidateRejectRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
) -> JSONResponse:
    return success_json(
        await decisions.reject(session, actor, candidate_id, version=body.version, reason=body.reason, note=body.note)
    )


@router.post("/{candidate_id}/reopen")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def reopen(
    candidate_id: uuid.UUID,
    body: CandidateVersion,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "decide")),
) -> JSONResponse:
    """驳回的改判回待审。"""

    return success_json(await decisions.reopen(session, actor, candidate_id, version=body.version))
