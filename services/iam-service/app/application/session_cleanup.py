"""清理已失效的会话与刷新令牌。

会话和刷新令牌只会新增、不会自然消失：每次登录和每次刷新都各写一行。
没有清理任务的话这两张表会一直涨下去（开发环境几天就攒了 300+ 行）。

判定「已失效」只看两件事：会话已过期，或者会话已被撤销。
两者都再额外保留 ``session_retention_days`` 天，便于回溯近期登录情况。
真正在用的会话不会被碰到。

删除顺序必须先令牌后会话：``iam_refresh_tokens.session_id`` 是
ON DELETE RESTRICT，反过来会被外键挡住。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from platform_common.clock import utcnow
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.domain.models import RefreshToken, Session


@dataclass(frozen=True)
class CleanupResult:
    """一次清理的结果。``*_remaining`` 是清理后剩余行数，便于观察增长趋势。"""

    tokens_deleted: int
    sessions_deleted: int
    tokens_remaining: int
    sessions_remaining: int


def _cutoff(retention_days: int, *, now: datetime | None = None) -> datetime:
    return (now or utcnow()) - timedelta(days=retention_days)


def _dead_session_ids(cutoff: datetime) -> ScalarSelect[uuid.UUID]:
    """已过期或已撤销、且超过保留期的会话 ID。"""

    return (
        select(Session.id)
        .where(
            or_(
                Session.expires_at < cutoff,
                Session.revoked_at.is_not(None) & (Session.revoked_at < cutoff),
            )
        )
        .scalar_subquery()
    )


async def cleanup_sessions(
    session: AsyncSession,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> CleanupResult:
    cutoff = _cutoff(retention_days, now=now)
    dead = _dead_session_ids(cutoff)

    # 先删令牌：session_id 外键是 RESTRICT，先删会话会被挡住。
    tokens = await session.execute(
        delete(RefreshToken).where(RefreshToken.session_id.in_(dead)).returning(RefreshToken.id)
    )
    tokens_deleted = len(tokens.all())

    sessions = await session.execute(
        delete(Session).where(Session.id.in_(_dead_session_ids(cutoff))).returning(Session.id)
    )
    sessions_deleted = len(sessions.all())

    await session.commit()

    tokens_remaining = int(await session.scalar(select(func.count()).select_from(RefreshToken)) or 0)
    sessions_remaining = int(await session.scalar(select(func.count()).select_from(Session)) or 0)
    return CleanupResult(
        tokens_deleted=tokens_deleted,
        sessions_deleted=sessions_deleted,
        tokens_remaining=tokens_remaining,
        sessions_remaining=sessions_remaining,
    )
