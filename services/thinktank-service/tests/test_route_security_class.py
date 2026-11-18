"""静态检查：智库所有路由必须声明安全级别，并登记了正确的资源与动作权限。"""

from __future__ import annotations

from platform_common.route_audit import audit_routes, permission_map

from app.main import app

FAVORITE_ROUTES = {
    "POST /api/v1/thinktank/knowledge/{file_id}/favorite",
    "DELETE /api/v1/thinktank/knowledge/{file_id}/favorite",
}


def test_every_route_is_classified() -> None:
    issues = audit_routes(app)
    assert issues == []


def test_every_non_public_route_uses_authoritative_permission() -> None:
    entries = permission_map(app)
    assert entries
    for method_path, (resource, action) in entries.items():
        assert resource == "thinktank.knowledge"
        method = method_path.split(" ", 1)[0]
        if method_path in FAVORITE_ROUTES:
            assert action == "favorite"
        elif method in {"POST", "PATCH", "PUT", "DELETE"}:
            assert action in {"create", "update", "delete", "upload_tags"}
        else:
            assert action in {"list", "read", "preview", "download", "export", "export_undefined"}
