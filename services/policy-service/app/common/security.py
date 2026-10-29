"""本服务的鉴权依赖。逻辑在 platform_common.service_authz，这里只绑定本服务配置。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.service_authz import (
    authorize_request,
    build_permission_dependency,
    cached_authz_client,
    classified,
)

from app.core.config import Settings, get_settings

__all__ = ["SecurityClass", "check_permission", "classified", "get_authz_client", "require_policy_permission"]


def get_authz_client(settings: Annotated[Settings, Depends(get_settings)]) -> AuthzClient:
    return cached_authz_client(
        base_url=settings.iam_base_url,
        service_name="policy-service",
        service_secret=settings.iam_service_secret,
        timeout_seconds=settings.iam_authorize_timeout_seconds,
    )


require_policy_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(get_authz_client)


async def check_permission(request: Request, resource: str, action: str) -> None:
    """接口里按运行时才知道的资源再校验一次，不通过抛 PermissionDeniedError。"""

    await authorize_request(get_authz_client(get_settings()), request, resource, action)
