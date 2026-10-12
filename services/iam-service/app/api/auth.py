"""认证接口。路径保留 /api/v1/auth/*，与网关一致。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from platform_common.errors import UnauthenticatedError
from platform_common.request_context import get_request_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import clear_auth_cookies, set_csrf_cookie, set_refresh_cookie
from app.api.schemas import CsrfPayload, LoginRequest, MePayload, PasswordChangeRequest, TokenPayload
from app.api.security import (
    CurrentPrincipal,
    check_csrf,
    check_origin,
    classified,
    require_authenticated,
    require_restricted_or_authenticated,
)
from app.application import auth_service
from app.application.auth_service import AuthService
from app.application.authorization import visible_permissions
from app.core.config import Settings, get_settings
from app.core.database import SessionLocal, get_db_session
from app.core.http_utils import client_ip, client_user_agent, success_json
from app.core.rate_limit import LoginRateLimiter
from app.core.redis_client import redis_client
from app.domain.enums import SecurityClass
from app.domain.tokens import generate_csrf_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _token_response(
    access: str,
    refresh: str,
    *,
    must_change_password: bool,
    settings: Settings,
) -> JSONResponse:
    payload = TokenPayload(
        access_token=access,
        expires_in=settings.access_token_ttl_seconds,
        must_change_password=must_change_password,
    )
    response = success_json(payload.model_dump())
    set_refresh_cookie(response, refresh, settings)
    set_csrf_cookie(response, generate_csrf_token(), settings)
    return response


@router.get("/csrf")
@classified(SecurityClass.PUBLIC_AUTH)
async def issue_csrf(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """页面刷新后获取 CSRF 值：返回新的 csrf_token 并写入可读 Cookie。"""

    token = generate_csrf_token()
    response = success_json(CsrfPayload(csrf_token=token).model_dump())
    set_csrf_cookie(response, token, settings)
    return response


@router.post("/login")
@classified(SecurityClass.PUBLIC_AUTH)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    limiter = LoginRateLimiter(redis_client, settings)
    ip = client_ip(request)
    username = body.username
    await limiter.assert_allowed(username, ip)
    service = AuthService(session, settings)
    try:
        user = await service.authenticate_password(username, body.password)
        access, refresh, _session_row = await service.login_success(
            user,
            request_id=get_request_id(),
            client_ip=ip,
            user_agent=client_user_agent(request),
        )
        await limiter.clear(username, ip)
        return _token_response(access, refresh, must_change_password=user.must_change_password, settings=settings)
    except UnauthenticatedError as exc:
        await limiter.record_failure(username, ip)
        async with SessionLocal() as fail_session:
            fail_service = AuthService(fail_session, settings)
            await fail_service.record_login_failure(
                username=username,
                request_id=get_request_id(),
                client_ip=ip,
                reason="unauthenticated",
            )
            await fail_session.commit()
        raise exc


@router.post("/refresh")
@classified(SecurityClass.PUBLIC_AUTH)
async def refresh(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    check_origin(request, settings)
    check_csrf(request, settings)
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise UnauthenticatedError("缺少刷新凭据")
    service = AuthService(session, settings)
    access, new_refresh, _session_row, user = await service.refresh(raw)
    if new_refresh is None:
        payload = TokenPayload(
            access_token=access,
            expires_in=settings.access_token_ttl_seconds,
            must_change_password=user.must_change_password,
        )
        return success_json(payload.model_dump())
    return _token_response(access, new_refresh, must_change_password=user.must_change_password, settings=settings)


@router.post("/logout")
@classified(SecurityClass.RESTRICTED_SESSION)
async def logout(
    request: Request,
    principal: CurrentPrincipal = Depends(require_restricted_or_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> Response:
    check_origin(request, settings)
    check_csrf(request, settings)
    service = AuthService(session, settings)
    await service.logout(principal.session)
    response = Response(status_code=204)
    clear_auth_cookies(response, settings)
    return response


@router.post("/logout-all")
@classified(SecurityClass.AUTHENTICATED)
async def logout_all(
    request: Request,
    principal: CurrentPrincipal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    check_origin(request, settings)
    check_csrf(request, settings)
    service = AuthService(session, settings)
    count = await service.logout_all(principal.user)
    response = success_json({"revoked": count})
    clear_auth_cookies(response, settings)
    return response


@router.get("/me")
@classified(SecurityClass.RESTRICTED_SESSION)
async def me(
    principal: CurrentPrincipal = Depends(require_restricted_or_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    user = principal.user
    is_superadmin, roles = await auth_service.role_summary(session, user.id)
    payload = MePayload(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        must_change_password=user.must_change_password,
        status=user.status,
        is_superadmin=is_superadmin,
        roles=roles,
    )
    return success_json(payload.model_dump())


@router.get("/permissions")
@classified(SecurityClass.AUTHENTICATED)
async def permissions(
    principal: CurrentPrincipal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:

    return success_json(await visible_permissions(session, principal.user.id))


@router.put("/password")
@classified(SecurityClass.RESTRICTED_SESSION)
async def change_password(
    body: PasswordChangeRequest,
    principal: CurrentPrincipal = Depends(require_restricted_or_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    service = AuthService(session, settings)
    access, refresh, _session_row = await service.change_password(principal.user, body.old_password, body.new_password)
    return _token_response(access, refresh, must_change_password=False, settings=settings)
