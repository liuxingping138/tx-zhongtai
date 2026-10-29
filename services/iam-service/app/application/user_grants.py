"""角色之外单独给某个人授权。

和角色授权同一套规则：只授已发布的叶子模块，档位只有查看 / 导出 / 管理。「权限分配」永远不单独给人：
它能给别人（包括自己）加权限，只跟着超级管理员角色走。调用方先校验「权限分配」可管理。
"""

from __future__ import annotations

import uuid

from platform_common.clock import utcnow
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.user_admin import assert_can_manage_target
from app.domain.authorization import SYSTEM_PERMISSIONS_CODE
from app.domain.enums import GrantLevel, NodeType, UserStatus
from app.domain.models import User
from app.repositories import outbox as outbox_repo
from app.repositories import resources as resource_repo
from app.repositories import user_grants as grant_repo
from app.repositories import users as user_repo

LEVELS = {GrantLevel.READ, GrantLevel.EXPORT, GrantLevel.FULL}


async def _live_user(session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False) -> User:
    user = await (
        user_repo.get_user_for_update(session, user_id) if lock else user_repo.get_user_by_id(session, user_id)
    )
    if user is None or user.status == UserStatus.DELETED:
        raise NotFoundError("用户不存在")
    return user


async def list_grants(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    user = await _live_user(session, user_id)
    pairs = await grant_repo.list_for_user(session, user.id)
    return {"grants": [{"resource_code": code, "level": level} for code, level in pairs], "version": user.version}


async def replace_grants(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    grants: list[tuple[str, str]],
    *,
    version: int | None = None,
) -> dict[str, object]:
    user = await _live_user(session, user_id, lock=True)
    await assert_can_manage_target(session, actor, user)
    if version is not None and version != user.version:
        raise VersionConflictError("这个人刚被别人改过（角色、授权或基本信息），请关闭后重新打开再改")
    codes = [code for code, level in grants if level != "NONE"]
    if len(set(codes)) != len(codes):
        # 原来照单写进去，撞主键回 500。
        raise ApiError("同一个模块出现了两次，请刷新后重新选择")
    normalized: list[tuple[uuid.UUID, str]] = []
    for resource_code, level in grants:
        if level == "NONE":
            continue
        if level not in LEVELS:
            raise ApiError("授权等级无效")
        resource = await resource_repo.get_resource_by_code(session, resource_code)
        if resource is None or not resource.published or resource.node_type != NodeType.RESOURCE:
            raise PermissionDeniedError("未知、未发布的资源或目录节点不能授权")
        if resource.code == SYSTEM_PERMISSIONS_CODE:
            raise PermissionDeniedError("「权限分配」只跟着超级管理员角色，不能单独授给个人")
        normalized.append((resource.id, str(level)))
    await grant_repo.replace_for_user(session, user.id, normalized, updated_by=actor.id)
    user.version += 1
    user.updated_at = utcnow()
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.grants_replaced",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(user.id),
            "grants": {code: level for code, level in grants if level != "NONE"},
            "outcome": "success",
        },
    )
    return await list_grants(session, user.id)
