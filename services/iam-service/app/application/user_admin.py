"""用户管理用例。"""

from __future__ import annotations

import secrets
import uuid

from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth_service import normalize_username
from app.core.clock import utcnow
from app.domain.authorization import remaining_loginable_superadmins
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import UserStatus
from app.domain.models import User
from app.domain.password import hash_password, validate_password_policy
from app.repositories import outbox as outbox_repo
from app.repositories import roles as role_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if len(normalized) < 3 or len(normalized) > 64:
        raise ApiError("用户名长度须为 3-64 个字符")
    if normalized[0] not in set("abcdefghijklmnopqrstuvwxyz"):
        raise ApiError("用户名须以字母开头")
    if any(ch not in USERNAME_CHARS for ch in normalized):
        raise ApiError("用户名仅允许字母、数字、点、下划线和连字符")
    return normalized


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(18)


def user_public(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "status": user.status,
        "must_change_password": user.must_change_password,
        "version": user.version,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


async def _assert_can_manage_target(session: AsyncSession, actor: User, target: User) -> None:
    actor_is_super = await user_repo.user_has_builtin_superadmin(session, actor.id)
    target_is_super = await user_repo.user_has_builtin_superadmin(session, target.id)
    if target_is_super and not actor_is_super:
        await outbox_repo.enqueue_independent(
            event_type="iam.user.protect_denied",
            payload={
                "actor_id": str(actor.id),
                "target_id": str(target.id),
                "outcome": "denied",
                "reason": "protected_superadmin",
            },
        )
        raise PermissionDeniedError("不能管理受保护的超级管理员账号")


async def _guard_last_superadmin(
    session: AsyncSession,
    target: User,
    *,
    new_status: str | None = None,
    remove_role: bool = False,
) -> None:
    locked = await user_repo.lock_superadmin_users(session)
    if not any(row.id == target.id for row in locked) and not remove_role:
        return
    remaining = remaining_loginable_superadmins(
        [(row.id, row.status) for row in locked],
        target_id=target.id,
        target_new_status=new_status,
        remove_role=remove_role,
    )
    if remaining < 1:
        await outbox_repo.enqueue_independent(
            event_type="iam.superadmin.protect",
            payload={"target_id": str(target.id), "outcome": "denied", "reason": "last_superadmin"},
        )
        raise PermissionDeniedError("不能移除最后一个可登录超级管理员")


async def list_users_page(
    session: AsyncSession,
    *,
    username: str | None,
    status: str | None,
    page: int,
    page_size: int,
    sort: str,
) -> tuple[list[dict[str, object]], int]:
    if sort not in {"created_at", "username"}:
        raise ApiError("不支持的排序字段")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await user_repo.count_users(session, username=username, status=status)
    rows = await user_repo.list_users(
        session,
        username=username,
        status=status,
        offset=(page - 1) * page_size,
        limit=page_size,
        sort=sort,
    )
    return [user_public(row) for row in rows], total


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    user = await user_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    payload = user_public(user)
    payload["role_ids"] = [str(item) for item in await user_repo.list_user_role_ids(session, user.id)]
    return payload


async def create_user(
    session: AsyncSession,
    actor: User,
    *,
    username: str,
    display_name: str,
    password: str | None,
) -> tuple[dict[str, object], str | None]:
    normalized = validate_username(username)
    display = display_name.strip()
    if not display:
        raise ApiError("显示名不能为空")
    temporary: str | None = None
    raw_password = password
    if raw_password is None:
        temporary = generate_temporary_password()
        raw_password = temporary
    policy_error = validate_password_policy(raw_password)
    if policy_error:
        raise ApiError(policy_error)
    now = utcnow()
    user = User(
        id=uuid.uuid4(),
        username=normalized,
        display_name=display,
        password_hash=hash_password(raw_password),
        status=UserStatus.ACTIVE,
        must_change_password=True,
        version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise VersionConflictError("用户名已存在") from exc
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.created",
        payload={"actor_id": str(actor.id), "target_id": str(user.id), "username": user.username, "outcome": "success"},
    )
    return user_public(user), temporary


async def update_user(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    *,
    display_name: str | None,
    status: str | None,
    version: int,
) -> dict[str, object]:
    user = await user_repo.get_user_for_update(session, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    if user.version != version:
        raise VersionConflictError()
    await _assert_can_manage_target(session, actor, user)
    if status is not None and status != user.status:
        if status not in {UserStatus.ACTIVE, UserStatus.DISABLED, UserStatus.ARCHIVED}:
            raise ApiError("无效的用户状态")
        if status != UserStatus.ACTIVE:
            await _guard_last_superadmin(session, user, new_status=status)
        user.status = status
        if status != UserStatus.ACTIVE:
            await session_repo.revoke_user_sessions(session, user.id)
    if display_name is not None:
        display = display_name.strip()
        if not display:
            raise ApiError("显示名不能为空")
        user.display_name = display
    user.updated_at = utcnow()
    user.version += 1
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.updated",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(user.id),
            "status": user.status,
            "outcome": "success",
        },
    )
    return user_public(user)


async def reset_password(session: AsyncSession, actor: User, user_id: uuid.UUID) -> str:
    user = await user_repo.get_user_for_update(session, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    await _assert_can_manage_target(session, actor, user)
    temporary = generate_temporary_password()
    user.password_hash = hash_password(temporary)
    user.must_change_password = True
    user.password_changed_at = utcnow()
    user.updated_at = utcnow()
    user.version += 1
    await session_repo.revoke_user_sessions(session, user.id)
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.password_reset",
        payload={"actor_id": str(actor.id), "target_id": str(user.id), "outcome": "success"},
    )
    return temporary


async def revoke_sessions(session: AsyncSession, actor: User, user_id: uuid.UUID) -> int:
    user = await user_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    await _assert_can_manage_target(session, actor, user)
    count = await session_repo.revoke_user_sessions(session, user.id)
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.sessions_revoked",
        payload={"actor_id": str(actor.id), "target_id": str(user.id), "revoked_count": count, "outcome": "success"},
    )
    return count


async def replace_roles(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    role_ids: list[uuid.UUID],
    *,
    version: int,
) -> dict[str, object]:
    user = await user_repo.get_user_for_update(session, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    if user.version != version:
        raise VersionConflictError()
    await _assert_can_manage_target(session, actor, user)
    unique_ids = list(dict.fromkeys(role_ids))
    roles = await role_repo.get_roles_by_ids(session, unique_ids)
    if len(roles) != len(unique_ids):
        raise ApiError("存在未知角色")
    had_super = await user_repo.user_has_builtin_superadmin(session, user.id)
    will_have_super = any(role.code == SUPERADMIN_ROLE_CODE and role.is_builtin for role in roles)
    if had_super and not will_have_super:
        await _guard_last_superadmin(session, user, remove_role=True)
    await user_repo.replace_user_roles(session, user.id, unique_ids, granted_by=actor.id)
    user.updated_at = utcnow()
    user.version += 1
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.roles_replaced",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(user.id),
            "role_ids": [str(item) for item in unique_ids],
            "outcome": "success",
        },
    )
    payload = user_public(user)
    payload["role_ids"] = [str(item) for item in unique_ids]
    return payload
