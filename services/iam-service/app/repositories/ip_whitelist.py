"""访问白名单查询。表很小（几十到几百行），列表不分页。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserStatus
from app.domain.models import IpWhitelistEntry, User

LIST_LIMIT = 1000
USER_OPTION_LIMIT = 20


async def list_entries(session: AsyncSession) -> list[tuple[IpWhitelistEntry, User]]:
    """全部白名单连同对应的人，到期晚的在前（没到期的自然排在前面）。已删除账号的不列。"""

    stmt = (
        select(IpWhitelistEntry, User)
        .join(User, User.id == IpWhitelistEntry.user_id)
        .where(User.status != UserStatus.DELETED)
        .order_by(IpWhitelistEntry.expires_at.desc())
        .limit(LIST_LIMIT)
    )
    return [(entry, user) for entry, user in (await session.execute(stmt)).all()]


async def active_ranges_for_user(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[tuple[str, datetime]]:
    """这个人此刻有效的 (IP或网段, 到期时间)。鉴权时查，走 (user_id, expires_at) 索引。"""

    stmt = select(IpWhitelistEntry.ip_range, IpWhitelistEntry.expires_at).where(
        IpWhitelistEntry.user_id == user_id, IpWhitelistEntry.expires_at > now
    )
    return [(ip_range, expires_at) for ip_range, expires_at in (await session.execute(stmt)).all()]


async def get_entry(session: AsyncSession, entry_id: uuid.UUID) -> IpWhitelistEntry | None:
    stmt = select(IpWhitelistEntry).where(IpWhitelistEntry.id == entry_id).with_for_update()
    return (await session.scalars(stmt)).one_or_none()


async def find_active_duplicate(
    session: AsyncSession,
    user_id: uuid.UUID,
    ip_range: str,
    now: datetime,
    *,
    exclude_id: uuid.UUID | None = None,
) -> IpWhitelistEntry | None:
    stmt = select(IpWhitelistEntry).where(
        IpWhitelistEntry.user_id == user_id,
        IpWhitelistEntry.ip_range == ip_range,
        IpWhitelistEntry.expires_at > now,
    )
    if exclude_id is not None:
        stmt = stmt.where(IpWhitelistEntry.id != exclude_id)
    return (await session.scalars(stmt.limit(1))).first()


async def search_users(session: AsyncSession, keyword: str) -> list[User]:
    """开通时选人：按账号或姓名包含关键词，只列启用的账号。"""

    stmt = select(User).where(User.status == UserStatus.ACTIVE)
    text = keyword.strip()
    if text:
        pattern = f"%{text}%"
        stmt = stmt.where(or_(User.username.ilike(pattern), User.display_name.ilike(pattern)))
    stmt = stmt.order_by(User.display_name, User.username).limit(USER_OPTION_LIMIT)
    return list((await session.scalars(stmt)).all())


def add(session: AsyncSession, entry: IpWhitelistEntry) -> None:
    session.add(entry)


async def remove(session: AsyncSession, entry: IpWhitelistEntry) -> None:
    await session.delete(entry)
