"""本地权限组件：IAM 接口与内部 authorize 共用，避免 HTTP 自调用。"""

from __future__ import annotations

import uuid

from platform_common.errors import PermissionDeniedError, UnauthenticatedError
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_outbox import enqueue_independent
from app.domain.authorization import AuthzDecision, evaluate_authorization
from app.domain.enums import UserStatus
from app.domain.models import MenuItem, User
from app.repositories import resources as resource_repo
from app.repositories import users as user_repo

logger = get_logger(__name__)
_WRITE_ACTIONS = {"create", "update", "reset_password", "revoke_sessions", "grant", "purge"}
_SUPERADMIN_ACTIONS = {"purge"}

_DECISION_MESSAGE = {
    AuthzDecision.DENY_UNPUBLISHED: "未发布资源不可访问",
    AuthzDecision.DENY_UNKNOWN: "未知资源或动作",
    AuthzDecision.DENY_LEVEL: "没有执行该操作的权限",
    AuthzDecision.DENY_ACCOUNT: "账号不可用",
}


async def resolve_authorization(
    session: AsyncSession,
    user: User,
    resource_code: str,
    action_code: str,
) -> tuple[AuthzDecision, str | None]:
    resource = await resource_repo.get_resource_by_code(session, resource_code)
    action = await resource_repo.get_action(session, resource.id, action_code) if resource is not None else None
    levels = await resource_repo.list_effective_levels(session, user.id)
    decision = evaluate_authorization(
        account_active=user.status == UserStatus.ACTIVE,
        resource_published=None if resource is None else resource.published,
        action_required_level=None if action is None else action.required_level,
        effective_level=levels.get(resource_code),
    )
    return decision, levels.get(resource_code)


async def is_allowed(session: AsyncSession, user: User, resource_code: str, action_code: str) -> bool:
    """只判断不拒绝，也不记越权审计：用于「有权限就多做一步」的场景，没有权限是正常分支。"""

    decision, _level = await resolve_authorization(session, user, resource_code, action_code)
    return decision == AuthzDecision.ALLOW


async def assert_allowed(session: AsyncSession, user: User, resource_code: str, action_code: str) -> str | None:
    decision, level = await resolve_authorization(session, user, resource_code, action_code)
    if decision == AuthzDecision.ALLOW:
        return level
    if action_code in _WRITE_ACTIONS:
        try:
            await enqueue_independent(
                event_type="iam.authz.denied",
                payload={
                    "actor_id": str(user.id),
                    "actor_name": user.display_name,
                    "resource_code": resource_code,
                    "action_code": action_code,
                    "reason": decision.value,
                    "outcome": "denied",
                },
            )
        except Exception:  # noqa: BLE001  拒绝审计写入失败不能改变「拒绝」结论，只记日志
            logger.warning("authz_denied_outbox_failed", resource=resource_code, action=action_code)
    raise PermissionDeniedError(_DECISION_MESSAGE[decision])


async def authorize_access_context(
    session: AsyncSession,
    user: User,
    resource_code: str,
    action_code: str,
) -> dict[str, object]:
    if user.status != UserStatus.ACTIVE:
        raise UnauthenticatedError("账号不可用")
    if user.must_change_password:
        raise PermissionDeniedError("请先修改初始密码后再使用系统")
    decision, level = await resolve_authorization(session, user, resource_code, action_code)
    allowed = decision == AuthzDecision.ALLOW
    reason = None if allowed else _DECISION_MESSAGE[decision]
    if (
        allowed
        and action_code in _SUPERADMIN_ACTIONS
        and not await user_repo.user_has_builtin_superadmin(session, user.id)
    ):
        allowed = False
        reason = "仅超级管理员可清空数据"
    return {
        "allowed": allowed,
        "reason": reason,
        "level": level,
        "resource": resource_code,
        "action": action_code,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "status": user.status,
        },
    }


async def visible_permissions(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    levels = await resource_repo.list_effective_levels(session, user_id)
    resources = await resource_repo.list_all_resources(session)
    menus = await resource_repo.list_all_menus(session)
    resource_by_id = {item.id: item for item in resources}
    visible_menus: list[dict[str, object]] = []
    for menu in menus:
        if not menu.enabled:
            continue
        if menu.resource_id is None:
            # 目录菜单：仅当存在可见子资源时由前端再过滤；这里仍要求目录自身启用
            visible_menus.append(_menu_payload(menu, None))
            continue
        resource = resource_by_id.get(menu.resource_id)
        if resource is None or not resource.published:
            continue
        if resource.code not in levels:
            continue
        visible_menus.append(_menu_payload(menu, resource.code))
    return {
        "resources": [{"code": code, "level": level} for code, level in sorted(levels.items())],
        "menus": visible_menus,
    }


def _menu_payload(menu: MenuItem, resource_code: str | None) -> dict[str, object]:
    return {
        "id": str(menu.id),
        "parent_id": str(menu.parent_id) if menu.parent_id else None,
        "title": menu.title,
        "route_name": menu.route_name,
        "resource_code": resource_code,
        "icon": menu.icon,
        "sort_order": menu.sort_order,
    }
