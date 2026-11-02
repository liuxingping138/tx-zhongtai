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

from app.api.schemas import ScenarioPatch, ScenarioWrite
from app.api.security import classified, require_codebook_permission
from app.application import scenarios as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/codebook/scenarios", tags=["codebook-scenarios"])
RESOURCE = "codebook.scenarios"


def scenario_filters(
    industry_scenario_code: list[str] | None = Query(default=None),
    industry_l1: list[str] | None = Query(default=None),
    scenario_tag: list[str] | None = Query(default=None),
    customer_group_name: list[str] | None = Query(default=None),
    is_new_scenario: list[str] | None = Query(default=None),
) -> Filters:
    return {
        "industry_scenario_code": industry_scenario_code,
        "industry_l1": industry_l1,
        "scenario_tag": scenario_tag,
        "customer_group_name": customer_group_name,
        "is_new_scenario": is_new_scenario,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(scenario_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        await service.list_scenarios(
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
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_scenario_options(session))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
) -> JSONResponse:
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await service.search_scenario_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/paths")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_paths(
    q: str = Query(..., min_length=1, max_length=100),
    industry_l1: str | None = Query(default=None, max_length=128),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
) -> JSONResponse:
    """按名称找码表里的行业场景路径（按客群去重），页面上选场景用：合并目标、改某一行的场景。"""

    return success_json({"items": await service.search_paths(session, keyword=q, industry_l1=industry_l1)})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(scenario_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
) -> Response:
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_scenarios(
        session,
        actor,
        filters,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="scenarios.xlsx"'},
    )


@router.post("/import", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
) -> Response:
    content = await read_import_upload(request, settings.import_max_bytes)
    return import_result_response(await service.import_scenarios(session, actor, content), "scenarios-import.xlsx")


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: ScenarioWrite,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(
        await service.create_scenario(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.get_scenario(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: ScenarioPatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_scenario(session, actor, item_id, body.model_dump(exclude_unset=True)))
