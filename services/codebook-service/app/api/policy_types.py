from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PolicyTypeWrite
from app.api.security import classified, require_codebook_permission
from app.application import policy_types as service
from app.application.actors import Actor
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter(prefix="/api/v1/codebook/policy-types", tags=["codebook-policy-types"])
RESOURCE = "codebook.policy_types"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_codebook_permission(RESOURCE, "list")),
):
    return success_json(await service.list_policy_types(session, keyword=keyword, page=page, page_size=page_size))


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "export")),
):
    payload = await service.export_policy_types(session, actor)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="policy-types.xlsx"'},
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
    return success_json(await service.import_policy_types(session, actor, content))


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
    body: PolicyTypeWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_codebook_permission(RESOURCE, "update")),
):
    return success_json(await service.update_policy_type(session, actor, item_id, body.model_dump()))
