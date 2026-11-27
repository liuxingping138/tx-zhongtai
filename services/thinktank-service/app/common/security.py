"""本服务的鉴权依赖。逻辑在 platform_common.service_authz，这里只绑定本服务配置。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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

__all__ = [
    "LibraryAccess",
    "SecurityClass",
    "classified",
    "fetch_scope_levels",
    "get_authz_client",
    "get_library_access",
    "require_thinktank_permission",
]


def get_authz_client(settings: Annotated[Settings, Depends(get_settings)]) -> AuthzClient:
    return cached_authz_client(
        base_url=settings.iam_base_url,
        service_name="thinktank-service",
        service_secret=settings.iam_service_secret,
        timeout_seconds=settings.iam_authorize_timeout_seconds,
    )


# 一次鉴权顺带拉回智库全量资源与二维范围档位（knowledge/reports/proposals + file_type.*/industry_type.*）
SCOPE_PREFIXES: tuple[str, ...] = ("thinktank.",)

# send_client_ip：智库只在公司网络能用，IAM 鉴权时按来源 IP 核对公司网络和这个人的访问白名单（系统管理 → 访问白名单），
# 不通过回 403 NETWORK_DENIED。每次请求（含 PDF 每一段 Range）都随鉴权核对，白名单删了或到期下一个请求就拦。
require_thinktank_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(
    get_authz_client,
    scope_prefixes=SCOPE_PREFIXES,
    send_client_ip=True,
)


async def fetch_scope_levels(
    request: Request,
    client: AuthzClient,
    resources: list[str],
    action: str,
) -> dict[str, str]:
    """批量查询当前用户在范围资源上的授权档位。"""

    return await resource_levels(request, client, resources, action)


_VALID_LEVELS = frozenset({"READ", "EXPORT", "FULL"})
_LIBRARY_PATH_RESOURCES: tuple[tuple[str, str], ...] = (
    ("/api/v1/thinktank/reports", "thinktank.reports"),
    ("/api/v1/thinktank/proposals", "thinktank.proposals"),
)


def _library_resource_from_path(path: str) -> str | None:
    for prefix, resource in _LIBRARY_PATH_RESOURCES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return resource
    return None


@dataclass(frozen=True)
class LibraryAccess:
    """普通子库（报告库、方案库）基于子库档位与独立下载权限的能力视图。"""

    level: str = "NONE"
    allow_download: bool = False

    @property
    def can_read(self) -> bool:
        return self.level in _VALID_LEVELS

    @property
    def can_download(self) -> bool:
        return self.allow_download and self.can_read

    @property
    def can_export(self) -> bool:
        return self.level in {"EXPORT", "FULL"}

    @property
    def can_edit(self) -> bool:
        return self.level == "FULL"


def get_library_access(request: Request) -> LibraryAccess:
    """从鉴权依赖写入的 request.state.authz_scopes / authz_level 构造当前子库操作能力。"""

    scopes = getattr(request.state, "authz_scopes", None)
    resource = _library_resource_from_path(request.url.path)
    if isinstance(scopes, dict) and resource is not None:
        raw_level = scopes.get(resource)
        raw_download = scopes.get(f"{resource}.download")
        level = raw_level if isinstance(raw_level, str) and raw_level in _VALID_LEVELS else "NONE"
        allow_download = isinstance(raw_download, str) and raw_download in _VALID_LEVELS
        return LibraryAccess(level=level, allow_download=allow_download)
    raw_level = getattr(request.state, "authz_level", None)
    level = raw_level if isinstance(raw_level, str) and raw_level in _VALID_LEVELS else "NONE"
    return LibraryAccess(level=level)
