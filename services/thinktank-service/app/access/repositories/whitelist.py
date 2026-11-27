"""白名单查询。表很小（几十行），不分页。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.domain.models import IpWhitelistEntry

LIST_LIMIT = 1000


async def list_entries(session: AsyncSession) -> list[IpWhitelistEntry]:
    """全部白名单，没到期的在前、到期晚的在前。"""

    stmt = select(IpWhitelistEntry).order_by(IpWhitelistEntry.expires_at.desc()).limit(LIST_LIMIT)
    return list((await session.scalars(stmt)).all())


async def active_ranges(session: AsyncSession, now: datetime) -> list[tuple[str, datetime]]:
    """此刻还有效的 (IP或网段, 到期时间)。每个智库请求都会查一次，走到期时间索引。"""

    stmt = select(IpWhitelistEntry.ip_range, IpWhitelistEntry.expires_at).where(IpWhitelistEntry.expires_at > now)
    return [(ip_range, expires_at) for ip_range, expires_at in (await session.execute(stmt)).all()]


async def get_entry(session: AsyncSession, entry_id: uuid.UUID, *, for_update: bool = False) -> IpWhitelistEntry | None:
    stmt = select(IpWhitelistEntry).where(IpWhitelistEntry.id == entry_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.scalars(stmt)).one_or_none()


async def find_active_same_range(
    session: AsyncSession, ip_range: str, now: datetime, *, exclude_id: uuid.UUID | None = None
) -> IpWhitelistEntry | None:
    stmt = select(IpWhitelistEntry).where(IpWhitelistEntry.ip_range == ip_range, IpWhitelistEntry.expires_at > now)
    if exclude_id is not None:
        stmt = stmt.where(IpWhitelistEntry.id != exclude_id)
    return (await session.scalars(stmt.limit(1))).first()


def add(session: AsyncSession, entry: IpWhitelistEntry) -> None:
    session.add(entry)


async def delete(session: AsyncSession, entry: IpWhitelistEntry) -> None:
    await session.delete(entry)
