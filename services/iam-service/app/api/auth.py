"""认证接口。路径保留 /api/v1/auth/*，与网关一致。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from platform_common.errors import UnauthenticatedError
from platform_common.logging_setup import get_logger
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
from app.application.audit_outbox import enqueue_independent
from app.application.auth_service import AuthService
from app.application.authorization import visible_permissions
from app.core.config import Settings, get_settings
from app.core.database import SideSessionLocal, get_db_session
from app.core.http_utils import client_ip, client_user_agent, success_json
from app.core.rate_limit import LoginLockedError, LoginRateLimiter
from app.core.redis_client import redis_client
from app.domain.enums import SecurityClass
from app.domain.models import User
from app.domain.tokens import generate_csrf_token

logger = get_logger(__name__)
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
    check_origin(request, settings)
    limiter = LoginRateLimiter(redis_client, settings)
    ip = client_ip(request)
    user_agent = client_user_agent(request)
    username = body.username
    try:
        await limiter.reserve(username, ip)
    except LoginLockedError as exc:
        # 锁定期间的尝试也进登录日志，管理员要能看到「有人还在试」；但每个锁定窗口只记一次。
        # 账号被锁和出口 IP 被限制分开写：后者是同一出口的所有人都登不上，处理办法不一样。
        reason = "locked_ip" if exc.by_ip else "locked_account"
        if await limiter.first_notice(username, ip, reason, exc.retry_after_seconds or 1):
            await _record_failure(settings, username, ip, user_agent, reason)
        raise
    service = AuthService(session, settings)
    try:
        user = await service.authenticate_password(username, body.password)
        access, refresh, _session_row = await service.login_success(
            user,
            request_id=get_request_id(),
            client_ip=ip,
            user_agent=user_agent,
        )
    except UnauthenticatedError as exc:
        # 占的这一次名额留着，就是一次失败。
        reason = "disabled" if exc.message == auth_service.ACCOUNT_UNAVAILABLE else "unauthenticated"
        await _record_failure(settings, username, ip, user_agent, reason)
        raise
    except Exception:
        # 库出错之类没走到验密码结果：不算一次失败。
        await limiter.release(username, ip)
        raise
    await limiter.succeeded(username, ip)
    return _token_response(access, refresh, must_change_password=user.must_change_password, settings=settings)


def _client(request: Request) -> dict[str, str]:
    return {"ip": client_ip(request), "user_agent": client_user_agent(request)}


async def _record_failure(settings: Settings, username: str, ip: str, user_agent: str, reason: str) -> None:
    """失败留痕放在独立会话里：请求本身的事务会因异常回滚。

    留痕写不进去（库出错、小连接池正忙）只记日志：不能把这次的 401 变成 500，失败次数照样记在 Redis 里。
    """

    try:
        async with SideSessionLocal() as fail_session:
            await AuthService(fail_session, settings).record_login_failure(
                username=username,
                request_id=get_request_id(),
                client_ip=ip,
                user_agent=user_agent,
                reason=reason,
            )
            await fail_session.commit()
    except Exception:  # 留痕失败不改变登录失败的结论
        logger.exception("login_failure_record_failed", reason=reason)


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
    await service.logout(principal.session, actor_name=principal.user.display_name, client=_client(request))
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
    count = await service.logout_all(principal.user, client=_client(request))
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
    request: Request,
    principal: CurrentPrincipal = Depends(require_restricted_or_authenticated),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    user, client = principal.user, _client(request)
    # 和登录共用失败计数：原密码输错按一次失败算，连错几次一样被锁，留下审计。
    limiter = LoginRateLimiter(redis_client, settings)
    await limiter.reserve(user.username, client["ip"])
    service = AuthService(session, settings)
    try:
        access, refresh, _session_row = await service.change_password(
            user, body.old_password, body.new_password, client=client
        )
    except auth_service.WrongOldPasswordError:
        await _record_password_failure(user, client)
        raise
    except Exception:
        await limiter.release(user.username, client["ip"])
        raise
    await limiter.succeeded(user.username, client["ip"])
    return _token_response(access, refresh, must_change_password=False, settings=settings)


async def _record_password_failure(user: User, client: dict[str, str]) -> None:
    """独立事务留痕：请求本身的事务会因异常回滚。写不进去只记日志，不改变这次的结果。"""

    try:
        await enqueue_independent(
            event_type="auth.password.change_failed",
            payload={
                "actor_id": str(user.id),
                "actor_name": user.display_name,
                "username": user.username,
                "client_ip": client["ip"],
                "user_agent": client["user_agent"],
                "request_id": get_request_id(),
                "reason": "wrong_old_password",
                "outcome": "failure",
            },
        )
    except Exception:  # 留痕失败不改变「原密码不正确」的结论
        logger.exception("password_failure_record_failed")
