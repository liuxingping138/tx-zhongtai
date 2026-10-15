from __future__ import annotations

from platform_common.route_audit import audit_routes, iter_api_routes, permission_map

from app.main import app

# 试发和对话只调用模型、不改数据，但会产生费用，挂的是 ask / chat 动作而不是只读动作。
READ_ACTIONS = {"list", "read", "export"}


def _api_route_keys() -> list[str]:
    return [
        f"{method} {route.path}"
        for route in iter_api_routes(app)
        if route.path.startswith("/api/")
        for method in sorted(route.methods or [])
    ]


def test_api_routes_pass_security_audit() -> None:
    issues = audit_routes(app)
    assert issues == [], "路由安全体检未通过:\n" + "\n".join(str(item) for item in issues)


def test_every_api_route_carries_an_ai_permission() -> None:
    mapping = permission_map(app)
    assert sorted(mapping) == sorted(_api_route_keys())
    wrong = {key: marker for key, marker in mapping.items() if not marker[0].startswith("ai.")}
    assert wrong == {}, f"以下路由挂到了别的服务的资源码: {wrong}"


def test_write_routes_require_write_actions() -> None:
    offenders = {
        key: marker
        for key, marker in permission_map(app).items()
        if key.split(" ", 1)[0] in {"POST", "PATCH", "PUT", "DELETE"} and marker[1] in READ_ACTIONS
    }
    assert offenders == {}, f"以下写接口挂的是只读动作: {offenders}"


def test_stream_routes_live_under_the_unbuffered_prefix() -> None:
    """网关只对 /api/v1/ai/stream 关掉缓冲和压缩，流式接口放错前缀就会攒满才下发。"""

    streaming = {route.path for route in iter_api_routes(app) if route.path.endswith(("/ask", "/chat"))}
    assert streaming == {"/api/v1/ai/stream/ask", "/api/v1/ai/stream/chat"}
