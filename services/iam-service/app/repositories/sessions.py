from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.models import RefreshToken, Session


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await session.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


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
