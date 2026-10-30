"""角色与授权接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.responses import paginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    RoleCopyRequest,
    RoleCreateRequest,
    RoleGrantsReplaceRequest,
    RoleMembersAddRequest,
    RoleUpdateRequest,
)
from app.api.security import CurrentPrincipal, classified, require_permission
from app.application import role_admin, user_admin
from app.application.authorization import assert_allowed, is_allowed
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter()


@router.get("/roles")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_roles(
    _principal: CurrentPrincipal = Depends(require_permission("system.roles", "list")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: list[str] | None = Query(default=None),
    name: list[str] | None = Query(default=None),
) -> JSONResponse:
    items, total = await role_admin.list_roles_page(session, status=status, name=name, page=page, page_size=page_size)
    return success_json(paginate(items, total, page=page, page_size=page_size).model_dump())


@router.get("/roles/{role_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_role(
    role_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.roles", "read")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json(await role_admin.get_role(session, role_id))


@router.post("/roles")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_role(
    body: RoleCreateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.roles", "create")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json(
        await role_admin.create_role(
            session, principal.user, code=body.code, name=body.name, description=body.description
        ),
        status_code=201,
    )


@router.patch("/roles/{role_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.roles", "update")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    enabling = body.status == "active"
    can_grant = enabling and await is_allowed(session, principal.user, "system.permissions", "grant")
    return success_json(
        await role_admin.update_role(
            session,
            principal.user,
            role_id,
            role_admin.RoleChanges(
                version=body.version, name=body.name, description=body.description, status=body.status
            ),
            can_grant=can_grant,
        )
    )


@router.get("/roles/{role_id}/grants")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_grants(
    role_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.permissions", "read")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json(await role_admin.list_grants(session, role_id))


@router.put("/roles/{role_id}/grants")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def replace_grants(
    role_id: uuid.UUID,
    body: RoleGrantsReplaceRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.permissions", "grant")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    grants: list[tuple[str, str]] = [(item.resource_code, item.level) for item in body.grants]
    return success_json(
        await role_admin.replace_grants(session, principal.user, role_id, version=body.version, grants=grants)
    )


@router.get("/resources")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_resources(
    _principal: CurrentPrincipal = Depends(require_permission("system.permissions", "read")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json({"tree": await role_admin.resource_tree(session)})


@router.post("/roles/{role_id}/copy")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def copy_role(
    role_id: uuid.UUID,
    body: RoleCopyRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.roles", "create")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    # 复制会连带授权，等同于一次授权操作，还要有「权限分配」可管理。
    await assert_allowed(session, principal.user, "system.permissions", "grant")
    return success_json(
        await role_admin.copy_role(session, principal.user, role_id, name=body.name, description=body.description),
        status_code=201,
    )


@router.get("/roles/{role_id}/members")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_role_members(
    role_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.roles", "read")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json({"items": await role_admin.list_members(session, role_id)})


@router.post("/roles/{role_id}/members")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def add_role_members(
    role_id: uuid.UUID,
    body: RoleMembersAddRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.permissions", "grant")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    await role_admin.get_role(session, role_id)  # 角色不存在时明确 404，而不是「存在未知角色」
    added = await user_admin.add_role_members(session, principal.user, role_id, body.user_ids)
    return success_json({"added": added, "items": await role_admin.list_members(session, role_id)})


@router.delete("/roles/{role_id}/members/{user_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def remove_role_member(
    role_id: uuid.UUID,
    user_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission("system.permissions", "grant")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    await role_admin.get_role(session, role_id)
    await user_admin.remove_role_member(session, principal.user, role_id, user_id)
    return success_json({"items": await role_admin.list_members(session, role_id)})
