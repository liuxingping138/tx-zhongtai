from __future__ import annotations

from platform_common.route_audit import audit_routes, permission_map

from app.api.security import AUDIT_RESOURCE
from app.main import app

COVERED = ("/api/", "/internal/")


def test_api_and_internal_routes_pass_security_audit() -> None:
    """既校验 @classified 声明，也校验权限依赖真的挂上了。"""

    issues = audit_routes(app, covered_prefixes=COVERED)
    assert issues == [], "路由安全体检未通过:\n" + "\n".join(str(item) for item in issues)


def test_query_routes_are_bound_to_the_audit_resource() -> None:
    """审计查询接口全部挂在 system.audit 上，只读动作。"""

    mapping = permission_map(app, covered_prefixes=COVERED)
    assert mapping, "审计查询接口一条都没挂权限依赖"
    assert all(resource == AUDIT_RESOURCE for resource, _ in mapping.values())
    assert all(action in {"list", "read"} for _, action in mapping.values())


def test_ingest_route_is_internal_only() -> None:
    """事件写入走内部凭据，不挂 RBAC 权限依赖，也不能被当成业务查询接口。"""

    mapping = permission_map(app, covered_prefixes=COVERED)
    assert "POST /internal/v1/audit/events" not in mapping
