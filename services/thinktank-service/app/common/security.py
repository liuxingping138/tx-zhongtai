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

require_thinktank_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(
    get_authz_client,
    scope_prefixes=SCOPE_PREFIXES,
)


async def fetch_scope_levels(
    request: Request,
    client: AuthzClient,
    resources: list[str],
    action: str,
) -> dict[str, str]:
    """批量查询当前用户在范围资源上的授权档位。"""

    return await resource_levels(request, client, resources, action)


@dataclass(frozen=True)
class LibraryAccess:
    """普通子库（报告库、方案库）基于单资源授权档位的能力视图。"""

    level: str = "NONE"

    @property
    def can_read(self) -> bool:
        return self.level in {"READ", "EXPORT", "FULL"}

    @property
    def can_export(self) -> bool:
        return self.level in {"EXPORT", "FULL"}

    @property
    def can_edit(self) -> bool:
        return self.level == "FULL"


def get_library_access(request: Request) -> LibraryAccess:
    """从鉴权依赖写入的 request.state.authz_level 构造当前子库操作能力。"""

    raw_level = getattr(request.state, "authz_level", None)
    level = raw_level if isinstance(raw_level, str) and raw_level in {"READ", "EXPORT", "FULL"} else "NONE"
    return LibraryAccess(level=level)
