"""在线用户和登录锁定：看谁在线、按设备下线、解锁输错密码被锁的账号。

两个说法分开：「有效登录」是没撤销、没过期的会话（刷新令牌 7 天内都有效）；「在线」是其中最近
online_window_seconds（30 分钟）内有过操作的。最近活跃时间由 auth_service.note_activity 按请求更新。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from platform_common.clock import utcnow
from platform_common.errors import ApiError, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.user_admin import assert_can_manage_target, manageable_ids
from app.core.rate_limit import LoginLockouts
from app.domain.enums import UserStatus
from app.domain.models import Session, User
from app.repositories import outbox as outbox_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo

CURRENT_DEVICE_MESSAGE = "这是你现在正在用的这台设备，要退出请点左下角账号里的「退出登录」"


def _session_public(row: Session, user: User, *, online_since: datetime) -> dict[str, object]:
    info: dict[str, Any] = row.client_info or {}
    return {
        "id": str(row.id),
        "user": {"id": str(user.id), "username": user.username, "display_name": user.display_name},
        "ip": str(info.get("ip") or ""),
        "user_agent": str(info.get("user_agent") or ""),
        "created_at": row.created_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
        "online": row.last_seen_at >= online_since,
    }


async def list_online(
    session: AsyncSession, actor: User, *, current_session_id: uuid.UUID, online_window_seconds: int
) -> dict[str, object]:
    """全部有效登录，每台设备标出：是否在线、是不是我现在用的这台、我能不能把它下线。"""

    now = utcnow()
    rows = await session_repo.list_active_sessions(session, now=now)
    manageable = await manageable_ids(session, actor, list({user.id for _row, user in rows}))
    online_since = now - timedelta(seconds=online_window_seconds)
    items = []
    for row, user in rows:
        item = _session_public(row, user, online_since=online_since)
        current = row.id == current_session_id
        item["current"] = current
        # 正在用的这台不给下线：等于退出登录，已经有「退出登录」入口；误点会把自己踢出去、没保存的编辑也丢了。
        item["can_manage"] = user.id in manageable and not current
        items.append(item)
    return {"items": items, "online_window_seconds": online_window_seconds}


async def revoke_one(
    session: AsyncSession, actor: User, session_id: uuid.UUID, *, current_session_id: uuid.UUID
) -> None:
    """只下线这一台设备；同一个人的其他设备不动。自己正在用的这台不在这里下线，要退出用「退出登录」。"""

    if session_id == current_session_id:
        raise ApiError(CURRENT_DEVICE_MESSAGE)
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


async def unlock_ip(session: AsyncSession, actor: User, ip: str, lockouts: LoginLockouts) -> bool:
    """解除一个出口 IP 的登录限制：同一出口（常是全公司）输错太多次时，所有人都登不上，不必等它到期。"""

    unlocked = await lockouts.unlock_ip(ip)
    if unlocked:
        await outbox_repo.enqueue(
            session,
            event_type="iam.login_ip.unlocked",
            payload={"actor_id": str(actor.id), "target_id": ip, "outcome": "success"},
        )
    return unlocked
