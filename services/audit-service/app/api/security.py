from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from platform_common.authz import AuthzClient
from platform_common.errors import InternalCallerRejectedError, UnauthenticatedError
from platform_common.request_context import get_request_id
from platform_common.route_audit import mark_permission_dependency
from platform_common.service_authz import cached_authz_client

from app.core.config import Settings, get_settings
from app.domain.enums import SecurityClass

AUDIT_RESOURCE = "system.audit"


def classified(security_class: SecurityClass) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__security_class__ = security_class  # type: ignore[attr-defined]
        return func

    return decorator


def require_internal_caller(request: Request, settings: Settings) -> str:
    service = (request.headers.get("x-internal-service") or "").strip()
    token = request.headers.get("x-internal-token") or ""
    expected = settings.internal_caller_secrets.get(service)
    given = token.encode()
    wanted = (expected or "").encode()
    if not service or not expected or len(given) != len(wanted) or not hmac.compare_digest(given, wanted):
        raise InternalCallerRejectedError()
    return service


def get_authz_client(settings: Annotated[Settings, Depends(get_settings)]) -> AuthzClient:
    return cached_authz_client(
        base_url=settings.iam_base_url,
        service_name="audit-service",
        service_secret=settings.iam_service_secret,
        timeout_seconds=settings.iam_authorize_timeout_seconds,
    )


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise UnauthenticatedError()
    return header[7:].strip()


def require_audit_permission(action: str) -> Callable[..., Any]:
    async def dependency(
        request: Request,
        client: Annotated[AuthzClient, Depends(get_authz_client)],
    ) -> None:
        _ = get_request_id()
        await client.authorize(access_token=_bearer_token(request), resource=AUDIT_RESOURCE, action=action)

    return mark_permission_dependency(dependency, resource=AUDIT_RESOURCE, action=action)
