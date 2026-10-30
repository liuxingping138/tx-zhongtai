"""本地权限组件：IAM 接口与内部 authorize 共用，避免 HTTP 自调用。"""

from __future__ import annotations

import uuid

from platform_common.errors import PermissionDeniedError, UnauthenticatedError
from platform_common.logging_setup import get_logger
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import authz_catalog
from app.application.audit_outbox import enqueue_independent
from app.domain.authorization import AuthzDecision, evaluate_authorization
from app.domain.enums import UserStatus
from app.domain.models import MenuItem, User
from app.repositories import resources as resource_repo
from app.repositories import users as user_repo

logger = get_logger(__name__)
# 业务服务经 authorize 被拒时记审计：同一个人、同一模块、同一动作这么久只记一次，页面轮询、反复点按钮不会刷屏。
DENIAL_AUDIT_SECONDS = 600
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
    """资源和动作查进程内目录（见 authz_catalog），这个人在该模块上的档位每次现查一条。

    账号不可用、资源或动作未知、未发布时不查档位：结论已经是拒绝。
    """

    entry = await authz_catalog.catalog.resource(session, resource_code, action_code)
    required = None if entry is None else entry.actions.get(action_code)
    active = user.status == UserStatus.ACTIVE
    level = None
    if active and entry is not None and entry.grantable and required is not None:
        level = await resource_repo.effective_level(session, user.id, entry.id)
    decision = evaluate_authorization(
        account_active=active,
        resource_published=None if entry is None else entry.published,
        action_required_level=required,
        effective_level=level,
    )
    return decision, level


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


async def audit_service_denial(redis: Redis, user: User, context: dict[str, object], caller: str) -> None:
    """业务服务（政策、码表、AI……）问 IAM 被拒：原来只有 IAM 自己的写接口留审计，看不出谁在试别的模块。
    独立事务写，失败只记日志，不改变「拒绝」的结论。"""

    resource, action = str(context["resource"]), str(context["action"])
    try:
        if not await redis.set(
            f"iam:authz:denied:{user.id}:{resource}:{action}", "1", nx=True, ex=DENIAL_AUDIT_SECONDS
        ):
            return
        await enqueue_independent(
            event_type="iam.authz.denied",
            payload={
                "actor_id": str(user.id),
                "actor_name": user.display_name,
                "resource_code": resource,
                "action_code": action,
                "reason": context["reason"],
                "caller": caller,
                "outcome": "denied",
            },
        )
    except Exception:  # noqa: BLE001  审计写不进去不能让鉴权报错，结论仍是拒绝
        logger.warning("service_denial_audit_failed", resource=resource, action=action)


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
