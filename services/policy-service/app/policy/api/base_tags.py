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
from app.policy.api.schemas import BaseTagPatch, BaseTagWrite
from app.policy.application import base_tags as service

router = APIRouter(prefix="/api/v1/policy/base-tags", tags=["policy-base-tags"])
RESOURCE = "policy.base_tags"


def base_tag_filters(
    policy_name: list[str] | None = Query(default=None, description="政策名称关键词，模糊匹配"),
    province_name: list[str] | None = Query(default=None),
    policy_types: list[str] | None = Query(default=None),
    is_penetrate: list[str] | None = Query(default=None),
    need_interpret: list[str] | None = Query(default=None),
    ai_status: list[str] | None = Query(default=None, description="打标状态：类型判断失败、解读失败、待解读等"),
) -> Filters:
    return {
        "policy_name": policy_name,
        "province_name": province_name,
        "policy_types": policy_types,
        "is_penetrate": is_penetrate,
        "need_interpret": need_interpret,
        "ai_status": ai_status,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(base_tag_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        await service.list_base_tags(
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
    return success_json(await service.list_base_tag_options(session))


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
        values = await service.search_base_tag_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(base_tag_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
) -> Response:
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_base_tags(
        session,
        actor,
        filters,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="policy-base-tags.xlsx"'},
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
    return import_result_response(await service.import_base_tags(session, actor, content), "base-tags-import.xlsx")


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: BaseTagWrite,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(
        await service.create_base_tag(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.get_base_tag(session, item_id))


@router.get("/{item_id}/content")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item_content(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    """正文按需从源库取，不进平台库。"""

    return success_json(await service.base_tag_content(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: BaseTagPatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_base_tag(session, actor, item_id, body.model_dump(exclude_unset=True)))
