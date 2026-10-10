"""用户管理接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.http_utils import IMPORT_FILE_OPENAPI, read_import_upload
from platform_common.responses import paginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UserCreateRequest, UserRolesReplaceRequest, UserUpdateRequest
from app.api.security import CurrentPrincipal, classified, require_permission
from app.application import user_admin, user_excel
from app.application.authorization import assert_allowed, is_allowed
from app.application.user_fields import NewUser, UserChanges
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass
from app.domain.filters import UserFilters

router = APIRouter()


def user_filters(
    username: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    # 角色 id 之外还接受 none，表示「待分配角色」。
    role_id: list[str] | None = Query(default=None),
    # 同时匹配用户名、显示名、电话、邮箱。
    keyword: list[str] | None = Query(default=None),
) -> UserFilters:
    return UserFilters(username=username, status=status, role_id=role_id, keyword=keyword)


@router.get("/users")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_users(
    _principal: CurrentPrincipal = Depends(require_permission("system.users", "list")),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    filters: UserFilters = Depends(user_filters),
    sort: str = "created_at",
) -> JSONResponse:
    items, total = await user_admin.list_users_page(session, filters, page=page, page_size=page_size, sort=sort)
    return success_json(paginate(items, total, page=page, page_size=page_size).model_dump())


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/users/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_users(
    _principal: CurrentPrincipal = Depends(require_permission("system.users", "export")),
    session: AsyncSession = Depends(get_db_session),
    filters: UserFilters = Depends(user_filters),
) -> Response:
    # 与列表同一套筛选，所见即所导。
    payload = await user_excel.export_users(session, filters)
    return Response(
        content=payload,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="users.xlsx"'},
    )


@router.post("/users/import", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_users(
    request: Request,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "import")),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """批量建账号。结果文件里有每个人的初始密码，只返回这一次。"""

    content = await read_import_upload(request, settings.import_max_bytes)
    # 角色列是否生效与页面建人同一门槛：分配角色即授权，需要「权限分配」可管理。
    can_grant = await is_allowed(session, principal.user, "system.permissions", "grant")
    outcome = await user_excel.import_users(session, principal.user, content, can_grant=can_grant)
    payload = await user_excel.build_import_result(outcome)
    return Response(
        content=payload,
        media_type=XLSX,
        headers={
            "Content-Disposition": 'attachment; filename="users-import.xlsx"',
            "X-Import-Rejected": "0",
            "X-Import-Inserted": str(len(outcome.created)),
            "X-Import-Updated": "0",
            "X-Import-Skipped": str(len(outcome.skipped)),
            "X-Import-Total": str(outcome.total),
            "Access-Control-Expose-Headers": (
                "X-Import-Rejected, X-Import-Inserted, X-Import-Updated, "
                "X-Import-Skipped, X-Import-Total, Content-Disposition"
            ),
        },
    )


@router.get("/users/{user_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_user(
    user_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.users", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(await user_admin.get_user(session, user_id))


@router.get("/users/{user_id}/permissions")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_user_permissions(
    user_id: uuid.UUID,
    _principal: CurrentPrincipal = Depends(require_permission("system.users", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """多个角色叠加后，这个人在每个模块上最终能做什么，以及来自哪个角色。"""

    return success_json(await user_admin.effective_permissions(session, user_id))


@router.post("/users")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_user(
    body: UserCreateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "create")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    if body.role_ids:
        # 分配角色即授权，与单独「分配角色」接口同一门槛，不因合并到建账号而放宽。
        await assert_allowed(session, principal.user, "system.permissions", "grant")
    data = NewUser(
        username=body.username,
        display_name=body.display_name,
        phone=body.phone,
        email=body.email,
        role_ids=body.role_ids,
        password=body.password,
    )
    user, temporary = await user_admin.create_user(session, principal.user, data)
    payload: dict[str, object] = {"user": user}
    if temporary is not None:
        payload["temporary_password"] = temporary
    return success_json(payload, status_code=201)


@router.patch("/users/{user_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "update")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(
        await user_admin.update_user(
            session,
            principal.user,
            user_id,
            UserChanges(
                version=body.version,
                display_name=body.display_name,
                phone=body.phone,
                email=body.email,
                status=body.status,
            ),
        )
    )


@router.delete("/users/{user_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_user(
    user_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "delete")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    await user_admin.delete_user(session, principal.user, user_id)
    return success_json({"deleted": True})


@router.post("/users/{user_id}/reset-password")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def reset_password(
    user_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "reset_password")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    temporary = await user_admin.reset_password(session, principal.user, user_id)
    return success_json({"temporary_password": temporary})


@router.post("/users/{user_id}/revoke-sessions")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def revoke_sessions(
    user_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "revoke_sessions")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    count = await user_admin.revoke_sessions(session, principal.user, user_id)
    return success_json({"revoked": count})


@router.put("/users/{user_id}/roles")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def replace_user_roles(
    user_id: uuid.UUID,
    body: UserRolesReplaceRequest,
    principal: CurrentPrincipal = Depends(require_permission("system.permissions", "grant")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(
        await user_admin.replace_roles(session, principal.user, user_id, body.role_ids, version=body.version)
    )
