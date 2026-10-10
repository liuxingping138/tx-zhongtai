"""业务服务的鉴权依赖。

policy / codebook 等业务服务的鉴权逻辑完全一致，只有服务名不同，
所以这里按服务名参数化，各服务只保留一行绑定。

依赖失败一律返回 503，绝不当作放行——见 AuthzClient。
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request

from platform_common.actors import Actor
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.errors import UnauthenticatedError
from platform_common.route_audit import mark_permission_dependency


def classified(security_class: SecurityClass) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """给路由标注安全分级，供路由安全用例检查。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__security_class__ = security_class  # type: ignore[attr-defined]
        return func

    return decorator


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise UnauthenticatedError()
    return header[7:].strip()


@functools.cache
def cached_authz_client(
    *, base_url: str, service_name: str, service_secret: str, timeout_seconds: float
) -> AuthzClient:
    """同一组配置只建一个 AuthzClient，复用它的 HTTP 连接池；配置不同（如测试换了地址）自然是另一个客户端。"""

    return AuthzClient(
        base_url=base_url,
        service_name=service_name,
        service_secret=service_secret,
        timeout_seconds=timeout_seconds,
    )


def build_permission_dependency(get_client: Callable[..., AuthzClient]) -> Callable[[str, str], Callable[..., Any]]:
    """构造本服务的 require_*_permission 工厂；服务名在 get_client 构造 AuthzClient 时已写入。"""

    def require_permission(resource: str, action: str) -> Callable[..., Any]:
        async def dependency(
            request: Request,
            # get_client 是闭包变量：本模块启用了延迟标注，写进 Annotated 会变成 FastAPI 解析不了的字符串，
            # 参数会被误当成查询参数。这里只能用默认值写法。
            client: AuthzClient = Depends(get_client),  # noqa: B008
        ) -> Actor:
            result = await client.authorize(access_token=_bearer_token(request), resource=resource, action=action)
            actor_id = result.user_id or ""
            actor_name = result.display_name or result.username or actor_id
            if not actor_id:
                raise UnauthenticatedError()
            return Actor(id=actor_id, name=actor_name)

        return mark_permission_dependency(dependency, resource=resource, action=action)

    return require_permission
