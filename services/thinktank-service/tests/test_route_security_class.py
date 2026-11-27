"""静态检查：智库所有路由必须声明安全级别，并登记了正确的资源与动作权限。"""

from __future__ import annotations

from platform_common.route_audit import audit_routes, permission_map

from app.main import app

EXPECTED_RESOURCE_BY_PREFIX = (
    ("/api/v1/thinktank/knowledge", "thinktank.knowledge"),
    ("/api/v1/thinktank/reports", "thinktank.reports"),
    ("/api/v1/thinktank/proposals", "thinktank.proposals"),
    ("/api/v1/thinktank/favorites", "thinktank.favorites"),
)


def _expected_resource(path: str) -> str:
    for prefix, resource in EXPECTED_RESOURCE_BY_PREFIX:
        if path == prefix or path.startswith(f"{prefix}/"):
            if path.endswith("/download"):
                return f"{resource}.download"
            return resource
    raise AssertionError(f"未归属的智库路由：{path}")


def test_every_route_is_classified() -> None:
    issues = audit_routes(app)
    assert issues == []


def test_every_non_public_route_uses_authoritative_permission() -> None:
    entries = permission_map(app)
    assert entries
    seen_resources: set[str] = set()
    for method_path, (resource, action) in entries.items():
        method, path = method_path.split(" ", 1)
        assert resource == _expected_resource(path)
        seen_resources.add(resource)
        if path.endswith("/download"):
            assert action == "download"
        elif path.endswith("/favorite"):
            assert action == "favorite"
        elif method in {"POST", "PATCH", "PUT", "DELETE"}:
            assert action in {"create", "update", "delete", "upload_tags"}
        else:
            assert action in {"list", "read", "preview", "export", "export_undefined"}
    assert seen_resources == {
        "thinktank.knowledge",
        "thinktank.knowledge.download",
        "thinktank.reports",
        "thinktank.reports.download",
        "thinktank.proposals",
        "thinktank.proposals.download",
        "thinktank.favorites",
    }
