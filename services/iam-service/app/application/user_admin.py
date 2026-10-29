"""用户管理用例。"""

from __future__ import annotations

import uuid

from platform_common.clock import utcnow
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_outbox import enqueue_independent
from app.application.user_fields import (
    NewUser,
    UserChanges,
    generate_temporary_password,
    normalize_email,
    normalize_phone,
    validate_display_name,
    validate_username,
)
from app.domain.authorization import max_level, remaining_loginable_superadmins
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import UserStatus
from app.domain.filters import UserFilters
from app.domain.models import Role, User
from app.domain.password import hash_password, validate_password_policy
from app.repositories import outbox as outbox_repo
from app.repositories import resources as resource_repo
from app.repositories import roles as role_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo


def user_public(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "phone": user.phone,
        "email": user.email,
        "status": user.status,
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_login_ip": user.last_login_ip,
        "version": user.version,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


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
        await enqueue_independent(
            event_type="iam.superadmin.protect",
            payload={"target_id": str(target.id), "outcome": "denied", "reason": "last_superadmin"},
        )
        raise PermissionDeniedError("不能移除最后一个可登录超级管理员")


def _require_live(user: User | None) -> User:
    if user is None or getattr(user, "status", None) == UserStatus.DELETED:
        raise NotFoundError("用户不存在")
    return user


def _role_brief(role: Role) -> dict[str, object]:
    return {"id": str(role.id), "name": role.name, "status": role.status, "is_builtin": role.is_builtin}


async def list_users_page(
    session: AsyncSession, filters: UserFilters, *, page: int, page_size: int, sort: str
) -> tuple[list[dict[str, object]], int]:
    if sort not in {"created_at", "username"}:
        raise ApiError("不支持的排序字段")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await user_repo.count_users(session, filters)
    rows = await user_repo.list_users(session, filters, offset=(page - 1) * page_size, limit=page_size, sort=sort)
    # 列表直接带上角色：管理员一眼能看出「谁是政策管理员」，不必逐个打开。
    roles = await user_repo.roles_for_users(session, [row.id for row in rows])
    items: list[dict[str, object]] = []
    for row in rows:
        payload = user_public(row)
        payload["roles"] = [_role_brief(role) for role in roles.get(row.id, [])]
        items.append(payload)
    return items, total


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    user = _require_live(await user_repo.get_user_by_id(session, user_id))
    payload = user_public(user)
    roles = (await user_repo.roles_for_users(session, [user.id])).get(user.id, [])
    payload["role_ids"] = [str(role.id) for role in roles]
    payload["roles"] = [_role_brief(role) for role in roles]
    return payload


async def create_user(session: AsyncSession, actor: User, data: NewUser) -> tuple[dict[str, object], str | None]:
    """建账号时可一并分配角色，同一事务内完成，避免「建了人忘了给角色」登录后一片空白。

    是否有权分配角色由调用方先校验（需要「权限分配」可管理）。返回的第二项是生成的临时口令。
    """

    normalized = validate_username(data.username)
    display = validate_display_name(data.display_name)
    phone = normalize_phone(data.phone)
    email = normalize_email(data.email)
    temporary: str | None = None
    password_hash = data.password_hash
    if password_hash is None:
        raw_password = data.password
        if raw_password is None:
            temporary = generate_temporary_password()
            raw_password = temporary
        policy_error = validate_password_policy(raw_password)
        if policy_error:
            raise ApiError(policy_error)
        password_hash = hash_password(raw_password)
    now = utcnow()
    user = User(
        id=uuid.uuid4(),
        username=normalized,
        display_name=display,
        phone=phone,
        email=email,
        password_hash=password_hash,
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
    if data.role_ids:
        payload = await _set_roles(session, actor, user, data.role_ids)
        return payload, temporary
    payload = user_public(user)
    payload["role_ids"] = []
    payload["roles"] = []
    return payload, temporary


async def update_user(
    session: AsyncSession, actor: User, user_id: uuid.UUID, changes: UserChanges
) -> dict[str, object]:
    user = _require_live(await user_repo.get_user_for_update(session, user_id))
    if user.version != changes.version:
        raise VersionConflictError()
    await assert_can_manage_target(session, actor, user)
    status = changes.status
    if status is not None and status != user.status:
        if status not in {UserStatus.ACTIVE, UserStatus.DISABLED}:
            raise ApiError("无效的用户状态")
        if status != UserStatus.ACTIVE:
            await _guard_last_superadmin(session, user, new_status=status)
        user.status = status
        if status != UserStatus.ACTIVE:
            await session_repo.revoke_user_sessions(session, user.id)
    if changes.display_name is not None:
        user.display_name = validate_display_name(changes.display_name)
    if changes.phone is not None:
        user.phone = normalize_phone(changes.phone)
    if changes.email is not None:
        user.email = normalize_email(changes.email)
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
    user = _require_live(await user_repo.get_user_for_update(session, user_id))
    await assert_can_manage_target(session, actor, user)
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
    user = _require_live(await user_repo.get_user_by_id(session, user_id))
    await assert_can_manage_target(session, actor, user)
    count = await session_repo.revoke_user_sessions(session, user.id)
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.sessions_revoked",
        payload={"actor_id": str(actor.id), "target_id": str(user.id), "revoked_count": count, "outcome": "success"},
    )
    return count


async def delete_user(session: AsyncSession, actor: User, user_id: uuid.UUID) -> None:
    """逻辑删除：账号从列表消失、不能登录，行仍留着对操作日志。同名用户名可以再建。"""

    user = _require_live(await user_repo.get_user_for_update(session, user_id))
    if actor.id == user.id:
        raise PermissionDeniedError("不能删除当前登录的账号")
    await assert_can_manage_target(session, actor, user)
    await _guard_last_superadmin(session, user, new_status=UserStatus.DELETED)
    user.status = UserStatus.DELETED
    user.updated_at = utcnow()
    user.version += 1
    await session_repo.revoke_user_sessions(session, user.id)
    await user_repo.clear_user_roles(session, user.id)
    await outbox_repo.enqueue(
        session,
        event_type="iam.user.deleted",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(user.id),
            "username": user.username,
            "outcome": "success",
        },
    )


async def replace_roles(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    role_ids: list[uuid.UUID],
    *,
    version: int,
) -> dict[str, object]:
    user = _require_live(await user_repo.get_user_for_update(session, user_id))
    if user.version != version:
        raise VersionConflictError()
    return await _set_roles(session, actor, user, role_ids)


async def add_role_members(session: AsyncSession, actor: User, role_id: uuid.UUID, user_ids: list[uuid.UUID]) -> int:
    """从角色一侧加人：在每个用户现有角色上追加该角色，规则与「给用户分配角色」完全一致。"""

    added = 0
    for user_id in dict.fromkeys(user_ids):
        user = _require_live(await user_repo.get_user_for_update(session, user_id))
        current = await user_repo.list_user_role_ids(session, user.id)
        if role_id in current:
            continue
        await _set_roles(session, actor, user, [*current, role_id])
        added += 1
    return added


async def remove_role_member(session: AsyncSession, actor: User, role_id: uuid.UUID, user_id: uuid.UUID) -> None:
    user = _require_live(await user_repo.get_user_for_update(session, user_id))
    current = await user_repo.list_user_role_ids(session, user.id)
    if role_id not in current:
        return
    await _set_roles(session, actor, user, [item for item in current if item != role_id])


async def effective_permissions(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    """用户在每个模块上的最终权限，以及来自哪些角色。停用角色列出但不计入。"""

    user = _require_live(await user_repo.get_user_by_id(session, user_id))
    grouped: dict[str, list[dict[str, object]]] = {}
    for code, level, role in await user_repo.list_user_grant_sources(session, user.id):
        grouped.setdefault(code, []).append(
            {"role_id": str(role.id), "role_name": role.name, "level": level, "active": role.status == "active"}
        )
    # 带上模块中文名和所属分组：只有用户管理权限的人拿不到资源树，也要能看懂。
    resources = await resource_repo.list_all_resources(session)
    by_id = {item.id: item for item in resources}
    by_code = {item.code: item for item in resources}
    items = []
    for code, sources in grouped.items():
        effective = max_level(str(item["level"]) for item in sources if item["active"])
        resource = by_code.get(code)
        parent = by_id.get(resource.parent_id) if resource and resource.parent_id else None
        items.append(
            {
                "resource_code": code,
                "resource_name": resource.name if resource else code,
                "group_name": parent.name if parent else "",
                "level": effective or "NONE",
                "sources": sources,
            }
        )
    return {"account_active": user.status == UserStatus.ACTIVE, "items": items}


async def _set_roles(session: AsyncSession, actor: User, user: User, role_ids: list[uuid.UUID]) -> dict[str, object]:
    await assert_can_manage_target(session, actor, user)
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
    payload["roles"] = [_role_brief(role) for role in roles]
    return payload
