from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import IMPORT_FILE_OPENAPI, import_result_response, read_import_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.policy.api.schemas import InterpretationPatch, InterpretationStatusRequest, InterpretationWrite
from app.policy.application import interpretation_status, scenario_sync
from app.policy.application import interpretations as service

router = APIRouter(prefix="/api/v1/policy/interpretations", tags=["policy-interpretations"])
RESOURCE = "policy.interpretations"


def interpretation_filters(
    policy_title: list[str] | None = Query(default=None, description="政策原文名称关键词，模糊匹配"),
    industry_l1: list[str] | None = Query(default=None),
    scenario_l1_name: list[str] | None = Query(default=None),
    opportunity_type: list[str] | None = Query(default=None),
    is_new_scenario: list[str] | None = Query(default=None),
    new_scenario_level: list[str] | None = Query(default=None),
    info_level: list[str] | None = Query(default=None),
    data_status: list[str] | None = Query(default=None),
) -> Filters:
    return {
        "policy_title": policy_title,
        "industry_l1": industry_l1,
        "scenario_l1_name": scenario_l1_name,
        "opportunity_type": opportunity_type,
        "is_new_scenario": is_new_scenario,
        "new_scenario_level": new_scenario_level,
        "info_level": info_level,
        "data_status": data_status,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(interpretation_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        await service.list_interpretations(
            session,
            filters,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_interpretation_options(session))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await service.search_interpretation_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(interpretation_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
) -> Response:
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_interpretations(
        session,
        actor,
        filters,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="policy-interpretations.xlsx"'},
    )


@router.post("/import", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
) -> Response:
    content = await read_import_upload(request, settings.import_max_bytes)
    return import_result_response(
        await service.import_interpretations(session, actor, content), "interpretations-import.xlsx"
    )


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: InterpretationWrite,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(
        await service.create_interpretation(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/new-scenarios")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def new_scenarios(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """人工验证过、还没同步进码表的新增场景条数，按钮上显示。"""

    return success_json(await scenario_sync.pending(session))


@router.post("/new-scenarios/sync")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def sync_new_scenarios(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "sync_scenarios")),
) -> JSONResponse:
    """把人工验证过的新增场景写进行业场景码表，编码回填到解读行。"""

    return success_json(await scenario_sync.sync(session, actor))


@router.post("/data-status")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def set_data_status(
    body: InterpretationStatusRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    """勾选多条批量改数据状态，人工核对完一次改成「人工验证」。"""

    return success_json(await interpretation_status.set_data_status(session, actor, body.ids, body.data_status))


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.get_interpretation(session, item_id))


@router.get("/{item_id}/content")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item_content(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """正文按需从源库取，不进平台库。"""

    return success_json(await service.interpretation_content(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: InterpretationPatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(
        await service.update_interpretation(session, actor, item_id, body.model_dump(exclude_unset=True))
    )
