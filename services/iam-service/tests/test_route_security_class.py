from __future__ import annotations

# 不要依赖同目录其他用例先设好环境变量，否则单独跑这个文件会在导入 app 时就失败。
from fastapi.routing import APIRoute
from platform_common.route_audit import audit_routes, permission_map

from app.main import app

COVERED = ("/api/", "/internal/")

# 认证类接口按设计不走 RBAC：登录/刷新是公开入口，改密和会话查询只需要有效会话。
NON_RBAC_PREFIXES = ("/api/v1/auth/",)


def test_api_and_internal_routes_pass_security_audit() -> None:
    """既校验 @classified 声明，也校验权限依赖真的挂上了。"""

    issues = audit_routes(app, covered_prefixes=COVERED)
    assert issues == [], "路由安全体检未通过:\n" + "\n".join(str(item) for item in issues)


def test_system_routes_all_carry_a_permission_dependency() -> None:
    """/api/v1/system/* 是后台管理接口，逐条都必须挂 RBAC 权限依赖。"""

    system_routes = [
        f"{method} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/system/")
        for method in sorted(route.methods or [])
    ]
    mapping = permission_map(app, covered_prefixes=COVERED)
    missing = [key for key in system_routes if key not in mapping]
    assert missing == [], f"以下系统管理路由没挂权限依赖: {missing}"
    assert all(resource.startswith("system.") for resource, _ in mapping.values())


def test_only_auth_routes_skip_rbac() -> None:
    """除认证接口和内部接口外，不允许出现没挂权限依赖的对外路由。"""

    mapping = permission_map(app, covered_prefixes=COVERED)
    unguarded = [
        f"{method} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in sorted(route.methods or [])
        if f"{method} {route.path}" not in mapping and not route.path.startswith(NON_RBAC_PREFIXES)
    ]
    assert unguarded == [], f"以下对外路由既不是认证接口也没挂权限依赖: {unguarded}"
