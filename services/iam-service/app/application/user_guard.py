"""用户管理权限范围判定。"""

from __future__ import annotations

import uuid

from platform_common.errors import PermissionDeniedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_outbox import enqueue_independent
from app.domain.authorization import SYSTEM_PERMISSIONS_CODE, levels_dominated
from app.domain.models import User
from app.repositories import resources as resource_repo
from app.repositories import users as user_repo


async def assert_can_manage_target(session: AsyncSession, actor: User, target: User) -> None:
    actor_is_super = await user_repo.user_has_builtin_superadmin(session, actor.id)
    target_is_super = await user_repo.user_has_builtin_superadmin(session, target.id)
    if target_is_super and not actor_is_super:
        await enqueue_independent(
            event_type="iam.user.protect_denied",
            payload={
                "actor_id": str(actor.id),
                "target_id": str(target.id),
                "outcome": "denied",
                "reason": "protected_superadmin",
            },
        )
        raise PermissionDeniedError("不能管理受保护的超级管理员账号")
    if not actor_is_super and actor.id != target.id:
        actor_levels = await resource_repo.list_effective_levels(session, actor.id)
        if actor_levels.get(SYSTEM_PERMISSIONS_CODE) != "FULL":
            target_levels = await resource_repo.list_effective_levels(session, target.id)
            if not levels_dominated(actor_levels, target_levels):
                await enqueue_independent(
                    event_type="iam.user.protect_denied",
                    payload={
                        "actor_id": str(actor.id),
                        "target_id": str(target.id),
                        "outcome": "denied",
                        "reason": "privilege_exceeds_actor",
                    },
                )
                raise PermissionDeniedError("不能管理权限超出自身范围的账号")


async def manageable_ids(session: AsyncSession, actor: User, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """这批人里当前操作人能管的（停用、删除、重置密码、下线、解锁、改角色）。列表据此给每行 can_manage。"""

    if await user_repo.user_has_builtin_superadmin(session, actor.id):
        return set(user_ids)
    candidates = set(user_ids) - await user_repo.builtin_superadmin_ids(session, user_ids)
    actor_levels = await resource_repo.list_effective_levels(session, actor.id)
    if actor_levels.get(SYSTEM_PERMISSIONS_CODE) == "FULL":
        return candidates
    # 一页几十个人一次查完，不逐人查一遍授权。
    others = [uid for uid in candidates if uid != actor.id]
    levels = await resource_repo.list_effective_levels_for_users(session, others)
    allowed = {uid for uid in others if levels_dominated(actor_levels, levels.get(uid, {}))}
    return allowed | (candidates & {actor.id})
