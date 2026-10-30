from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.clock import utcnow
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserStatus
from app.domain.models import RefreshToken, Session, User


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await session.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_session_with_user(
    session: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Session, User] | None:
    """访问令牌里的会话连同账号一条查出；会话不属于这个账号就查不到。每个受保护请求和 authorize 都走这里。"""

    result = await session.execute(
        select(Session, User).join(User, User.id == Session.user_id).where(Session.id == session_id, User.id == user_id)
    )
    row = result.first()
    return None if row is None else (row[0], row[1])


async def touch_last_seen(
    session: AsyncSession, session_id: uuid.UUID, *, now: datetime, stale_before: datetime
) -> bool:
    """把会话的「最近活跃」推到 now。只改停在 stale_before 之前的；这一行正被别的事务锁着就跳过，不等锁。"""

    target = (
        select(Session.id)
        .where(Session.id == session_id, Session.last_seen_at < stale_before)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    result = await session.execute(
        update(Session)
        .where(Session.id == target)
        .values(last_seen_at=now)
        .execution_options(synchronize_session=False)
    )
    return bool(getattr(result, "rowcount", 0))


async def get_refresh_token_for_update(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update())
    return result.scalar_one_or_none()


async def revoke_session(session: AsyncSession, session_row: Session, *, now: datetime | None = None) -> None:
    if session_row.revoked_at is None:
        session_row.revoked_at = now or utcnow()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, *, now: datetime | None = None) -> int:
    stamp = now or utcnow()
    result = await session.execute(
        update(Session).where(Session.family_id == family_id, Session.revoked_at.is_(None)).values(revoked_at=stamp)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
    stamp = now or utcnow()
    result = await session.execute(
        update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None)).values(revoked_at=stamp)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def session_is_usable(session_row: Session, *, now: datetime | None = None) -> bool:
    stamp = now or utcnow()
    if session_row.revoked_at is not None:
        return False
    return session_row.expires_at > stamp


async def list_active_sessions(session: AsyncSession, *, now: datetime) -> list[tuple[Session, User]]:
    """有效登录：没撤销、没过期的会话，连同账号；已删除的账号不列。最近活跃的在前。"""

    result = await session.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(Session.revoked_at.is_(None), Session.expires_at > now, User.status != UserStatus.DELETED)
        .order_by(Session.last_seen_at.desc())
    )
    return [(row[0], row[1]) for row in result.all()]
