"""路由安全体检的自测。

重点是反向验证：故意造出「声明了安全分级但没挂权限依赖」的路由，
确认体检能抓到。否则各服务里那句 `assert issues == []` 可能只是恒真。
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, FastAPI

from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.route_audit import audit_routes, iter_api_routes, permission_map
from platform_common.service_authz import build_permission_dependency, classified


def _fake_client() -> AuthzClient:
    return cast(AuthzClient, object())


require_permission = build_permission_dependency(_fake_client)


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/probe/guarded")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def guarded(_: Any = Depends(require_permission("probe.items", "list"))) -> dict[str, str]:
        return {}

    @app.post("/api/v1/probe/forgot-dependency")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def forgot_dependency() -> dict[str, str]:
        return {}

    @app.get("/api/v1/probe/undeclared")
    async def undeclared(_: Any = Depends(require_permission("probe.items", "read"))) -> dict[str, str]:
        return {}

    @app.get("/api/v1/probe/mislabelled")
    @classified(SecurityClass.HEALTH)
    async def mislabelled(
        _: Any = Depends(require_permission("probe.items", "export")),
    ) -> dict[str, str]:
        return {}

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {}

    return app


def test_factory_marks_the_dependency() -> None:
    dependency = require_permission("probe.items", "import")
    assert dependency.__authz_permission__ == ("probe.items", "import")


def test_audit_catches_route_that_declares_but_forgets_the_dependency() -> None:
    reasons = {(issue.path, issue.reason) for issue in audit_routes(_build_app())}
    assert ("/api/v1/probe/forgot-dependency", "声明了 resource_authorized 但没挂权限依赖") in reasons


def test_audit_catches_undeclared_and_mislabelled_routes() -> None:
    reasons = {(issue.path, issue.reason) for issue in audit_routes(_build_app())}
    assert ("/api/v1/probe/undeclared", "未声明安全分级") in reasons
    assert ("/api/v1/probe/mislabelled", "挂了权限依赖却声明为 health") in reasons


def test_audit_accepts_the_guarded_route_and_skips_health() -> None:
    paths = {issue.path for issue in audit_routes(_build_app())}
    assert "/api/v1/probe/guarded" not in paths
    assert "/health/live" not in paths


def test_permission_map_reports_resource_and_action() -> None:
    mapping = permission_map(_build_app())
    assert mapping["GET /api/v1/probe/guarded"] == ("probe.items", "list")
    assert "POST /api/v1/probe/forgot-dependency" not in mapping


def test_routes_from_included_routers_are_audited() -> None:
    """各服务的路由都经 include_router 挂载，体检必须展开它们，路由器级依赖也要算数。"""

    router = APIRouter()

    @router.get("/items")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def items() -> dict[str, str]:
        return {}

    @router.get("/forgot")
    async def forgot() -> dict[str, str]:
        return {}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/nested", dependencies=[Depends(require_permission("nested", "list"))])
    assert [route.path for route in iter_api_routes(app)] == ["/api/v1/nested/items", "/api/v1/nested/forgot"]
    assert permission_map(app)["GET /api/v1/nested/items"] == ("nested", "list")
    assert {(issue.path, issue.reason) for issue in audit_routes(app)} == {
        ("/api/v1/nested/forgot", "未声明安全分级"),
    }


def test_audit_fails_when_no_route_is_found() -> None:
    assert audit_routes(FastAPI())


def test_permission_dependency_does_not_leak_into_query_parameters() -> None:
    # 鉴权客户端是闭包里的依赖，标注写法不对时 FastAPI 会把它当成查询参数，所有受保护接口都会出错。
    schema = _build_app().openapi()
    parameters = schema["paths"]["/api/v1/probe/guarded"]["get"].get("parameters", [])
    assert [parameter["name"] for parameter in parameters] == []
