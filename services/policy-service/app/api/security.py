from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request
from platform_common.authz import AuthzClient
from platform_common.errors import UnauthenticatedError

from app.application.actors import Actor
from app.core.config import Settings, get_settings
from app.domain.enums import SecurityClass

_authz_client: AuthzClient | None = None


def classified(security_class: SecurityClass) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__security_class__ = security_class  # type: ignore[attr-defined]
        return func

    return decorator


def get_authz_client(settings: Settings = Depends(get_settings)) -> AuthzClient:
    global _authz_client
    if _authz_client is None:
        _authz_client = AuthzClient(
            base_url=settings.iam_base_url,
            service_name="policy-service",
            service_secret=settings.iam_service_secret,
            timeout_seconds=settings.iam_authorize_timeout_seconds,
        )
    return _authz_client


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise UnauthenticatedError()
    return header[7:].strip()


def require_policy_permission(resource: str, action: str) -> Callable[..., Any]:
    async def dependency(
        request: Request,
        client: AuthzClient = Depends(get_authz_client),
    ) -> Actor:
        result = await client.authorize(access_token=_bearer_token(request), resource=resource, action=action)
        actor_id = result.user_id or ""
        actor_name = result.display_name or result.username or actor_id
        if not actor_id:
            raise UnauthenticatedError()
        return Actor(id=actor_id, name=actor_name)

    return dependency
