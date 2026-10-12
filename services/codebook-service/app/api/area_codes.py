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

from app.api.schemas import AreaCodePatch, AreaCodeWrite
from app.api.security import classified, require_codebook_permission
from app.application import area_codes as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/codebook/area-codes", tags=["codebook-area-codes"])
RESOURCE = "codebook.area_codes"


def area_code_filters(
    prov_name: list[str] | None = Query(default=None),
    city_name: list[str] | None = Query(default=None),
    county_name: list[str] | None = Query(default=None),
) -> Filters:
    return {"prov_name": prov_name, "city_name": city_name, "county_name": county_name}


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(area_code_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        await service.list_area_codes(
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
    return success_json(await service.list_area_code_options(session))


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
        values = await service.search_area_code_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(area_code_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
) -> Response:
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_area_codes(
        session,
        actor,
        filters,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="area-codes.xlsx"'},
    )


@router.post("/resolve", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def resolve_items(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "resolve")),
    settings: Settings = Depends(get_settings),
) -> Response:
    content = await read_import_upload(request, settings.import_max_bytes)
    payload, matched, unmatched = await service.resolve_area_codes(session, actor, content)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="area-code-resolve.xlsx"',
            "X-Matched-Count": str(matched),
            "X-Unmatched-Count": str(unmatched),
            "Access-Control-Expose-Headers": "X-Matched-Count, X-Unmatched-Count, Content-Disposition",
        },
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
    return import_result_response(await service.import_area_codes(session, actor, content), "area-codes-import.xlsx")


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: AreaCodeWrite,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(
        await service.create_area_code(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.get_area_code(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: AreaCodePatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_area_code(session, actor, item_id, body.model_dump(exclude_unset=True)))
