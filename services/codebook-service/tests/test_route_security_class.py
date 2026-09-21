from __future__ import annotations

import os

os.environ.setdefault(
    "CODEBOOK_DATABASE_URL", "postgresql+asyncpg://codebook_app:test@localhost:5432/codebook_db"
)
os.environ.setdefault("CODEBOOK_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("CODEBOOK_AUDIT_INGEST_SECRET", "unit-test")

from fastapi.routing import APIRoute  # noqa: E402
from platform_common.route_audit import audit_routes, permission_map  # noqa: E402

from app.main import app  # noqa: E402

# 省市区解析是上传文件换回匹配结果，不落库，所以用 POST 挂 READ 级的 resolve 动作。
READ_LEVEL_POST_ROUTES = {"POST /api/v1/codebook/area-codes/resolve"}


def _api_route_keys() -> list[str]:
    return [
        f"{method} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in sorted(route.methods or [])
    ]


def test_api_routes_pass_security_audit() -> None:
    """既校验 @classified 声明，也校验权限依赖真的挂上了。"""

    issues = audit_routes(app)
    assert issues == [], "路由安全体检未通过:\n" + "\n".join(str(item) for item in issues)


def test_every_api_route_carries_a_permission_dependency() -> None:
    """codebook-service 没有公开业务接口，每条路由都必须能查到资源码和动作码。"""

    mapping = permission_map(app)
    assert sorted(mapping) == sorted(_api_route_keys())
    wrong_service = {
        key: marker for key, marker in mapping.items() if not marker[0].startswith("codebook.")
    }
    assert wrong_service == {}, f"以下路由挂到了别的服务的资源码: {wrong_service}"


def test_write_routes_require_write_actions() -> None:
    """写接口不能挂成只读动作，否则 READ 级账号就能改数据。"""

    read_actions = {"list", "read", "export", "resolve"}
    offenders = {
        key: marker
        for key, marker in permission_map(app).items()
        if key.split(" ", 1)[0] in {"POST", "PATCH", "PUT", "DELETE"}
        and marker[1] in read_actions
        and key not in READ_LEVEL_POST_ROUTES
    }
    assert offenders == {}, f"以下写接口挂的是只读动作: {offenders}"
