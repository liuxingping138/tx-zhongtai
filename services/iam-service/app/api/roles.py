"""角色与授权接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.responses import paginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RoleCreateRequest, RoleGrantsReplaceRequest, RoleUpdateRequest
from app.api.security import CurrentPrincipal, classified, require_permission
from app.application import role_admin
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter()


@router.get("/roles")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_roles(
    _principal: CurrentPrincipal = Depends(require_permission("system.roles", "list")),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: list[str] | None = Query(default=None),
) -> JSONResponse:
    items, total = await role_admin.list_roles_page(session, status=status, page=page, page_size=page_size)
    return success_json(paginate(items, total, page=page, page_size=page_size).model_dump())


@router.get("/roles/{role_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_role(
    role_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.roles", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(await role_admin.get_role(session, role_id))


@router.post("/roles")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_role(
    body: RoleCreateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.roles", "create")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(
        await role_admin.create_role(session, principal.user, code=body.code, name=body.name),
        status_code=201,
    )


@router.patch("/roles/{role_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.roles", "update")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(
        await role_admin.update_role(
            session, principal.user, role_id, name=body.name, status=body.status, version=body.version
        )
    )


@router.get("/roles/{role_id}/grants")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_grants(
    role_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.permissions", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(await role_admin.list_grants(session, role_id))


@router.put("/roles/{role_id}/grants")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def replace_grants(
    role_id: uuid.UUID,
    body: RoleGrantsReplaceRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.permissions", "grant")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    grants: list[tuple[str, str]] = [(item.resource_code, item.level) for item in body.grants]
    return success_json(
        await role_admin.replace_grants(
            session, principal.user, role_id, version=body.version, grants=grants
        )
    )


@router.get("/resources")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_resources(
    _principal: CurrentPrincipal = Depends(require_permission("system.permissions", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json({"tree": await role_admin.resource_tree(session)})
