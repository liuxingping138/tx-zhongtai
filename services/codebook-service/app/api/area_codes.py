from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AreaCodeWrite
from app.api.security import classified, require_codebook_permission
from app.application import area_codes as service
from app.application.actors import Actor
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter(prefix="/api/v1/codebook/area-codes", tags=["codebook-area-codes"])
RESOURCE = "codebook.area_codes"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    prov_name: str | None = Query(default=None),
    city_name: str | None = Query(default=None),
    county_name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    return success_json(
        await service.list_area_codes(
            session,
            prov_name=prov_name,
            city_name=city_name,
            county_name=county_name,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    return success_json(await service.list_area_code_options(session))


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
):
    payload = await service.export_area_codes(session, actor)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="area-codes.xlsx"'},
    )


@router.post("/resolve")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def resolve_items(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
    settings: Settings = Depends(get_settings),
):
    content = await file.read()
    if len(content) > settings.import_max_bytes:
        raise ApiError("导入文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=422)
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


@router.post("/import")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
):
    content = await file.read()
    if len(content) > settings.import_max_bytes:
        raise ApiError("导入文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return success_json(await service.import_area_codes(session, actor, content))


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: AreaCodeWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "create")),
):
    return success_json(
        await service.create_area_code(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "read")),
):
    return success_json(await service.get_area_code(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: AreaCodeWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "update")),
):
    return success_json(await service.update_area_code(session, actor, item_id, body.model_dump()))
