"""把 IAM Outbox 映射为审计写入体。不信任、不透传 source_service。"""

from __future__ import annotations

from typing import Any

from app.application.redact import redact
from app.domain.models import OutboxEvent

_EVENT_META: dict[str, tuple[str, str, str, str]] = {
    "auth.login.succeeded": ("auth", "login", "user", "登录成功"),
    "auth.login.failed": ("auth", "login", "user", "登录失败"),
    "auth.refresh.replayed": ("auth", "refresh", "session", "刷新令牌重放"),
    "auth.logout": ("auth", "logout", "session", "退出登录"),
    "auth.logout_all": ("auth", "logout_all", "user", "退出全部会话"),
    "auth.password.changed": ("auth", "password_change", "user", "修改密码"),
    "iam.user.created": ("system.users", "create", "user", "创建用户"),
    "iam.user.updated": ("system.users", "update", "user", "更新用户"),
    "iam.user.deleted": ("system.users", "delete", "user", "删除用户"),
    "iam.user.password_reset": ("system.users", "reset_password", "user", "重置密码"),
    "iam.user.sessions_revoked": ("system.users", "revoke_sessions", "user", "强制下线"),
    "iam.user.roles_replaced": ("system.users", "assign_roles", "user", "分配用户角色"),
    "iam.user.protect_denied": ("system.users", "protect", "user", "拒绝管理受保护用户"),
    "iam.superadmin.protect": ("system.users", "protect", "user", "保护最后超级管理员"),
    "iam.role.created": ("system.roles", "create", "role", "创建角色"),
    "iam.role.updated": ("system.roles", "update", "role", "更新角色"),
    "iam.role.grants_replaced": ("system.permissions", "grant", "role", "替换角色授权"),
    "iam.role.grant_denied": ("system.permissions", "grant", "role", "拒绝角色授权"),
    "iam.catalog.synced": ("system", "catalog_sync", "catalog", "同步资源清单"),
    "iam.admin.created": ("system.users", "admin_create", "user", "创建初始管理员"),
    "iam.authz.denied": ("system", "authorize", "resource", "鉴权拒绝"),
}


def _target_id(payload: dict[str, Any], target_type: str) -> str | None:
    for key in ("target_id", "role_id", "session_id", "user_id"):
        value = payload.get(key)
        if value:
            return str(value)
    if target_type == "user" and payload.get("username"):
        return str(payload["username"])
    return None


def _actor_name(payload: dict[str, Any]) -> str | None:
    for key in ("actor_name", "username"):
        value = payload.get(key)
        if value:
            return str(value)[:128]
    return None


def map_outbox_to_ingest(event: OutboxEvent) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    safe = redact(payload)
    module_code, action_code, target_type, label = _EVENT_META.get(
        event.event_type, ("iam", event.event_type, "event", event.event_type)
    )
    outcome = str(safe.get("outcome") or "success")
    actor = _actor_name(safe)
    target = _target_id(safe, target_type)
    summary_bits = [label]
    if actor:
        summary_bits.append(actor)
    if target:
        summary_bits.append(str(target))
    return {
        "event_id": str(event.event_id),
        "occurred_at": event.created_at.isoformat(),
        "schema_version": event.schema_version,
        "request_id": safe.get("request_id"),
        "actor_id": safe.get("actor_id"),
        "actor_name_snapshot": actor,
        "module_code": module_code,
        "action_code": action_code,
        "target_type": target_type,
        "target_id": target,
        "outcome": outcome,
        "error_code": safe.get("reason") or safe.get("error_code"),
        "client_ip": safe.get("client_ip"),
        "user_agent": safe.get("user_agent"),
        "changes": safe,
        "summary": " / ".join(str(item) for item in summary_bits if item),
    }
