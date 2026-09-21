"""本服务的鉴权依赖。逻辑在 platform_common.service_authz，这里只绑定本服务配置。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.service_authz import build_permission_dependency, classified

from app.core.config import Settings, get_settings

__all__ = ["SecurityClass", "classified", "get_authz_client", "require_codebook_permission"]

_authz_client: AuthzClient | None = None


def get_authz_client(settings: Settings = Depends(get_settings)) -> AuthzClient:
    global _authz_client
    if _authz_client is None:
        _authz_client = AuthzClient(
            base_url=settings.iam_base_url,
            service_name="codebook-service",
            service_secret=settings.iam_service_secret,
            timeout_seconds=settings.iam_authorize_timeout_seconds,
        )
    return _authz_client


require_codebook_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(
    service_name="codebook-service",
    get_client=get_authz_client,
)
