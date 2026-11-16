"""路由安全分类、当前会话解析、CSRF/Origin 检查。"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from platform_common.errors import PermissionDeniedError, UnauthenticatedError
from platform_common.route_audit import mark_permission_dependency
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import auth_service
from app.application.authorization import assert_allowed
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.jwt_tokens import decode_access_token
from app.domain.enums import SecurityClass
from app.domain.models import Session, User


def classified(security_class: SecurityClass) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__security_class__ = security_class  # type: ignore[attr-defined]  # 函数对象上挂自定义标记，mypy 不认识这个属性
        return func

    return decorator


@dataclass
class CurrentPrincipal:
    user: User
    session: Session
    claims: dict[str, Any]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise UnauthenticatedError()
    return header[7:].strip()


def check_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if not origin:
        if settings.environment == "production":
            raise PermissionDeniedError("缺少 Origin")
        return
    explicit = set(settings.csrf_allowed_origins) | set(settings.cors_allow_origins)
    # 生产环境若显式配了跨域/CSRF 白名单，严格只认白名单，不盲信请求头 Host。
    if explicit and settings.environment == "production":
        allowed = explicit
    else:
        allowed = set(explicit)
        host = (request.headers.get("host") or "").strip()
        if host:
            proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
            if settings.environment == "production" or settings.cookie_secure or proto == "https":
                allowed.add(f"https://{host}")
            else:
                allowed.add(f"http://{host}")
                allowed.add(f"https://{host}")
    if origin not in allowed:
        raise PermissionDeniedError("请求来源不被允许")


def check_csrf(request: Request, settings: Settings) -> None:
    header = request.headers.get(settings.csrf_header_name)
    cookie = request.cookies.get(settings.csrf_cookie_name)
    if not header or not cookie or header != cookie:
        raise PermissionDeniedError("CSRF 校验失败")


async def principal_from_access_token(
    token: str,
    session: AsyncSession,
    settings: Settings,
) -> CurrentPrincipal:
    claims = decode_access_token(token, settings)
    try:
        user_id = claims["sub"]
        session_id = claims["sid"]
    except KeyError as exc:
        raise UnauthenticatedError() from exc

    user, session_row = await auth_service.load_principal(session, uuid.UUID(user_id), uuid.UUID(session_id))
    await auth_service.note_activity(session_row, every_seconds=settings.session_touch_seconds)
    return CurrentPrincipal(user=user, session=session_row, claims=claims)


async def get_principal(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> CurrentPrincipal:
    return await principal_from_access_token(_bearer_token(request), session, settings)


async def require_authenticated(principal: CurrentPrincipal = Depends(get_principal)) -> CurrentPrincipal:
    if principal.user.must_change_password:
        raise PermissionDeniedError("请先修改初始密码后再使用系统")
    return principal


async def require_restricted_or_authenticated(
    principal: CurrentPrincipal = Depends(get_principal),
) -> CurrentPrincipal:
    return principal


def require_permission(resource: str, action: str) -> Callable[..., Any]:
    async def dependency(
        principal: CurrentPrincipal = Depends(require_authenticated),
        session: AsyncSession = Depends(get_db_session, scope="function"),
    ) -> CurrentPrincipal:

        await assert_allowed(session, principal.user, resource, action)
        return principal

    return mark_permission_dependency(dependency, resource=resource, action=action)
