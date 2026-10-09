from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.http_utils import IMPORT_FILE_OPENAPI, import_result_response, read_import_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PolicyTypePatch, PolicyTypeWrite
from app.api.security import classified, require_codebook_permission
from app.application import policy_types as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/codebook/policy-types", tags=["codebook-policy-types"])
RESOURCE = "codebook.policy_types"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    keyword: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    return success_json(await service.list_policy_types(session, keyword=keyword, page=page, page_size=page_size))


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    return success_json(await service.list_policy_type_options(session))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await service.search_policy_type_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    keyword: list[str] | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
):
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_policy_types(
        session,
        actor,
        {
            "keyword": keyword,
        },
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="policy-types.xlsx"'},
    )


@router.post("/import", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
):
    content = await read_import_upload(request, settings.import_max_bytes)
    return import_result_response(
        await service.import_policy_types(session, actor, content), "policy-types-import.xlsx"
    )


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: PolicyTypeWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "create")),
):
    return success_json(await service.create_policy_type(session, actor, body.model_dump()), status_code=201)


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: PolicyTypePatch,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "update")),
):
    return success_json(
        await service.update_policy_type(session, actor, item_id, body.model_dump(exclude_unset=True))
    )
