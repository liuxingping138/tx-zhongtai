"""路由安全体检的自测。

重点是反向验证：故意造出「声明了安全分级但没挂权限依赖」的路由，
确认体检能抓到。否则各服务里那句 `assert issues == []` 可能只是恒真。
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Depends, FastAPI

from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.route_audit import audit_routes, permission_map
from platform_common.service_authz import build_permission_dependency, classified


def _fake_client() -> AuthzClient:
    return cast(AuthzClient, object())


require_permission = build_permission_dependency(
    service_name="probe-service", get_client=_fake_client
)


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
