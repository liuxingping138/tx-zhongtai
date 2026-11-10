"""初始超级管理员创建。已存在则不改写密码。"""

from __future__ import annotations

import uuid

from platform_common.clock import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth_service import normalize_username
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import UserStatus
from app.domain.models import Role, User, UserRole
from app.domain.password import hash_password, validate_password_policy
from app.repositories import outbox as outbox_repo


class AdminCreateError(Exception):
    pass


async def create_initial_admin(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str = "系统管理员",
) -> tuple[User, bool]:
    """返回 (user, created)。created=False 表示已存在，密码未被改写。"""

    normalized = normalize_username(username)
    if not normalized:
        raise AdminCreateError("用户名不能为空")
    policy_error = validate_password_policy(password)
    if policy_error:
        raise AdminCreateError(policy_error)

    role_result = await session.execute(select(Role).where(Role.code == SUPERADMIN_ROLE_CODE))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise AdminCreateError("尚未同步内置角色，请先执行 make seed")

    existing = await session.execute(select(User).where(User.username == normalized, User.status != UserStatus.DELETED))
    user = existing.scalar_one_or_none()
    now = utcnow()
    if user is not None:
        changed = False
        if user.status == UserStatus.DISABLED:
            user.status = UserStatus.ACTIVE
            changed = True
        link = await session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
        if link.scalar_one_or_none() is None:
            session.add(UserRole(user_id=user.id, role_id=role.id, created_at=now))
            changed = True
        if changed:
            user.updated_at = now
            if user.version is not None:
                user.version += 1
        return user, False

    user = User(
        id=uuid.uuid4(),
        username=normalized,
        display_name=display_name,
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
        must_change_password=True,
        version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id, created_at=now))
    await outbox_repo.enqueue(
        session,
        event_type="iam.admin.created",
        payload={"actor_id": str(user.id), "username": user.username, "outcome": "success"},
    )
    return user, True
