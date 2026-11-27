"""业务服务的鉴权依赖。

policy / codebook 等业务服务的鉴权逻辑完全一致，只有服务名不同，
所以这里按服务名参数化，各服务只保留一行绑定。

依赖失败一律返回 503，绝不当作放行——见 AuthzClient。
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import Depends, Request

from platform_common.actors import Actor
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.errors import PermissionDeniedError, UnauthenticatedError
from platform_common.http_utils import client_ip
from platform_common.route_audit import mark_permission_dependency


def classified(security_class: SecurityClass) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """给路由标注安全分级，供路由安全用例检查。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__security_class__ = security_class  # type: ignore[attr-defined]  # 函数对象上挂自定义标记，mypy 不认识这个属性
        return func

    return decorator


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise UnauthenticatedError()
    return header[7:].strip()


async def authorize_request(client: AuthzClient, request: Request, resource: str, action: str) -> None:
    """按运行时才知道的资源再校验一次（如某个任务额外要求的权限）。

    不通过时由 client 抛 PermissionDeniedError。
    """

    await client.authorize(access_token=_bearer_token(request), resource=resource, action=action, **_ip_kwargs(request))


def _ip_kwargs(request: Request) -> dict[str, str]:
    """路由鉴权依赖开了 send_client_ip 时，同一请求里的其他鉴权调用也带上来源 IP（IAM 对限定网络的模块要核对）。"""

    ip = getattr(request.state, "authz_client_ip", None)
    return {"client_ip": ip} if isinstance(ip, str) and ip else {}


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


async def resource_levels(request: Request, client: AuthzClient, resources: list[str], action: str) -> dict[str, str]:
    """当前用户在几个资源上的授权档位，没授权的不在结果里。用于按数据分类收窄可见范围，不是路由的准入检查。

    若路由鉴权已通过 scope_prefixes 随同返回 scopes，直接复用，不再逐个发 HTTP 请求。
    被拒绝只说明没有这个分类；鉴权服务不可用等其他错误照常抛出（503），绝不当作放行。
    """

    preloaded = getattr(request.state, "authz_scopes", None)
    if action == "list" and isinstance(preloaded, dict):
        return {resource: preloaded[resource] for resource in resources if preloaded.get(resource)}

    token = _bearer_token(request)
    ip_kwargs = _ip_kwargs(request)

    async def level(resource: str) -> str | None:
        try:
            result = await client.authorize(access_token=token, resource=resource, action=action, **ip_kwargs)
        except PermissionDeniedError:
            return None
        return result.level or None

    levels = await asyncio.gather(*(level(resource) for resource in resources))
    return {resource: value for resource, value in zip(resources, levels, strict=True) if value}


def build_permission_dependency(
    get_client: Callable[..., AuthzClient],
    *,
    scope_prefixes: Sequence[str] | None = None,
    send_client_ip: bool = False,
) -> Callable[[str, str], Callable[..., Any]]:
    """构造本服务的 require_*_permission 工厂；服务名在 get_client 构造 AuthzClient 时已写入。

    send_client_ip：鉴权时带上来源 IP，IAM 据此对限定公司网络的模块核对访问白名单（智库开着）。
    """

    def require_permission(resource: str, action: str) -> Callable[..., Any]:
        async def dependency(
            request: Request,
            # get_client 是闭包变量：本模块启用了延迟标注，写进 Annotated 会变成 FastAPI 解析不了的字符串，
            # 参数会被误当成查询参数。这里只能用默认值写法。
            client: AuthzClient = Depends(get_client),  # noqa: B008  闭包依赖不能写成 Annotated，原因见上
        ) -> Actor:
            if send_client_ip:
                request.state.authz_client_ip = client_ip(request)
            result = await client.authorize(
                access_token=_bearer_token(request),
                resource=resource,
                action=action,
                scope_prefixes=scope_prefixes,
                **_ip_kwargs(request),
            )
            if result.level:
                request.state.authz_level = result.level
            if scope_prefixes and isinstance(getattr(result, "scopes", None), dict):
                request.state.authz_scopes = result.scopes
            actor_id = result.user_id or ""
            actor_name = result.display_name or result.username or actor_id
            if not actor_id:
                raise UnauthenticatedError()
            return Actor(id=actor_id, name=actor_name)

        return mark_permission_dependency(dependency, resource=resource, action=action)

    return require_permission
