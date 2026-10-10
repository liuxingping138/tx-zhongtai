"""路由安全体检。

各服务原来的 `test_route_security_class.py` 只校验路由声明了 `@classified`，
写了装饰器但忘了挂 `Depends(require_*_permission(...))` 照样能过——
装饰器只是个标记，真正拦请求的是依赖。这里把两件事合到一处校验。

校验三条不变量：

1. 覆盖范围内的路由必须声明安全分级。
2. 声明为 `resource_authorized` 的路由必须挂权限依赖，且资源码和动作码非空。
3. 挂了权限依赖的路由必须声明为 `resource_authorized`，避免错标成公开路由。

权限依赖由 `mark_permission_dependency` 打上 `__authz_permission__` 标记，
各服务的 `require_*_permission` 工厂负责调用它，这里只按标记识别。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, cast

from fastapi.routing import APIRoute

RESOURCE_AUTHORIZED_VALUE = "resource_authorized"


def mark_permission_dependency(dependency: Callable[..., Any], *, resource: str, action: str) -> Callable[..., Any]:
    """给鉴权依赖打标记，供路由体检识别。"""

    dependency.__authz_permission__ = (resource, action)  # type: ignore[attr-defined]  # 函数对象上挂自定义标记，mypy 不认识这个属性
    return dependency


@dataclass(frozen=True)
class RouteIssue:
    methods: str
    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.methods} {self.path}: {self.reason}"


def _security_class_value(route: APIRoute) -> str | None:
    declared = getattr(route.endpoint, "__security_class__", None)
    if declared is None:
        return None
    return str(getattr(declared, "value", declared))


def _walk_dependants(dependant: Any) -> Iterator[Any]:
    yield dependant
    for sub in dependant.dependencies:
        yield from _walk_dependants(sub)


def _permission_marker(route: APIRoute) -> tuple[str, str] | None:
    for dependant in _walk_dependants(route.dependant):
        marker = getattr(dependant.call, "__authz_permission__", None)
        if marker is not None:
            return cast("tuple[str, str]", marker)
    return None


def audit_routes(
    app: Any,
    *,
    covered_prefixes: tuple[str, ...] = ("/api/",),
    exempt_prefixes: tuple[str, ...] = ("/health",),
) -> list[RouteIssue]:
    """返回所有违反不变量的路由。返回空列表表示体检通过。"""

    issues: list[RouteIssue] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            continue
        if not any(path.startswith(prefix) for prefix in covered_prefixes):
            continue
        methods = ",".join(sorted(route.methods or []))
        declared = _security_class_value(route)
        marker = _permission_marker(route)

        if declared is None:
            issues.append(RouteIssue(methods, path, "未声明安全分级"))
        elif declared == RESOURCE_AUTHORIZED_VALUE and marker is None:
            issues.append(RouteIssue(methods, path, "声明了 resource_authorized 但没挂权限依赖"))
        elif marker is not None and declared != RESOURCE_AUTHORIZED_VALUE:
            issues.append(RouteIssue(methods, path, f"挂了权限依赖却声明为 {declared}"))

        if marker is not None:
            resource, action = marker
            if not resource or not action:
                issues.append(RouteIssue(methods, path, f"权限依赖的资源码或动作码为空: {marker!r}"))
    return issues


def permission_map(
    app: Any,
    *,
    covered_prefixes: tuple[str, ...] = ("/api/",),
    exempt_prefixes: tuple[str, ...] = ("/health",),
) -> dict[str, tuple[str, str]]:
    """导出「方法 + 路径 -> (资源码, 动作码)」，便于用例核对权限矩阵。"""

    mapping: dict[str, tuple[str, str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            continue
        if not any(path.startswith(prefix) for prefix in covered_prefixes):
            continue
        marker = _permission_marker(route)
        if marker is None:
            continue
        for method in sorted(route.methods or []):
            mapping[f"{method} {path}"] = marker
    return mapping
