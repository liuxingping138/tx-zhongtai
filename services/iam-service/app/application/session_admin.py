"""在线用户和登录锁定：看谁在线、按设备下线、解锁输错密码被锁的账号。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.clock import utcnow
from platform_common.errors import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.user_admin import assert_can_manage_target
from app.core.rate_limit import LoginLockouts
from app.domain.enums import UserStatus
from app.domain.models import Session, User
from app.repositories import outbox as outbox_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo


def _session_public(row: Session, user: User) -> dict[str, object]:
    info: dict[str, Any] = row.client_info or {}
    return {
        "id": str(row.id),
        "user": {"id": str(user.id), "username": user.username, "display_name": user.display_name},
        "ip": str(info.get("ip") or ""),
        "user_agent": str(info.get("user_agent") or ""),
        "created_at": row.created_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
    }


async def list_online(session: AsyncSession) -> list[dict[str, object]]:
    rows = await session_repo.list_active_sessions(session, now=utcnow())
    return [_session_public(row, user) for row, user in rows]


async def revoke_one(session: AsyncSession, actor: User, session_id: uuid.UUID) -> None:
    """只下线这一台设备；同一个人的其他设备不动。"""

    row = await session_repo.get_session(session, session_id)
    if row is None or not session_repo.session_is_usable(row):
        raise NotFoundError("这个会话已经下线")
    user = await user_repo.get_user_by_id(session, row.user_id)
    if user is None or user.status == UserStatus.DELETED:
        raise NotFoundError("这个会话已经下线")
    await assert_can_manage_target(session, actor, user)
    await session_repo.revoke_session(session, row)
    await outbox_repo.enqueue(
        session,
        event_type="iam.session.revoked",
        payload={"actor_id": str(actor.id), "target_id": str(user.id), "session_id": str(row.id), "outcome": "success"},
    )


async def with_lockouts(items: list[dict[str, object]], lockouts: LoginLockouts) -> list[dict[str, object]]:
    """给用户列表每人带上还要锁多少秒（没锁是 0）。"""

    remaining = await lockouts.remaining_seconds([str(item["username"]) for item in items])
    for item in items:
        item["locked_seconds"] = remaining.get(str(item["username"]), 0)
    return items


async def unlock(session: AsyncSession, actor: User, user_id: uuid.UUID, lockouts: LoginLockouts) -> bool:
    user = await user_repo.get_user_by_id(session, user_id)
    if user is None or user.status == UserStatus.DELETED:
        raise NotFoundError("用户不存在")
    await assert_can_manage_target(session, actor, user)
    unlocked = await lockouts.unlock(user.username)
    if unlocked:
        await outbox_repo.enqueue(
            session,
            event_type="iam.user.unlocked",
            payload={"actor_id": str(actor.id), "target_id": str(user.id), "outcome": "success"},
        )
    return unlocked
