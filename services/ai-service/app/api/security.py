"""本服务的鉴权依赖。逻辑在 platform_common.service_authz，这里只绑定本服务配置。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.service_authz import (
    build_permission_dependency,
    cached_authz_client,
    classified,
    resource_levels,
)

from app.core.config import Settings, get_settings
from app.domain.categories import CATEGORIES, CategoryAccess, category_resource

__all__ = [
    "CategoryAccess",
    "SecurityClass",
    "classified",
    "get_authz_client",
    "get_category_access",
    "require_ai_permission",
]


def get_authz_client(settings: Annotated[Settings, Depends(get_settings)]) -> AuthzClient:
    return cached_authz_client(
        base_url=settings.iam_base_url,
        service_name="ai-service",
        service_secret=settings.iam_service_secret,
        timeout_seconds=settings.iam_authorize_timeout_seconds,
    )


require_ai_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(get_authz_client)


async def get_category_access(
    request: Request, client: Annotated[AuthzClient, Depends(get_authz_client)]
) -> CategoryAccess:
    """当前用户在各模板类型上的权限。只用来收窄范围，路由本身仍由 require_ai_permission 准入。"""

    levels = await resource_levels(request, client, [category_resource(code) for code in CATEGORIES], "list")
    return CategoryAccess.from_levels(levels)
