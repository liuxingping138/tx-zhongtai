"""按规则表的网站编码改信源的爬虫状态。"""

from __future__ import annotations

from datetime import datetime

from platform_common.actors import Actor
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.domain.fields import CRAWLER_STATUS_ONLINE, CRAWLER_STATUS_PENDING
from app.policy.domain.models import Source


async def mark_online(session: AsyncSession, codes: set[str], *, today: str, now: datetime, actor: Actor) -> list[str]:
    """未爬、没填状态的改成已爬，上线时间记 today；已爬、异常和其他人工填的状态不动。返回改了的网站编码。"""

    if not codes:
        return []
    result = await session.execute(
        update(Source)
        .where(Source.site_code.in_(codes), Source.crawler_status.in_(CRAWLER_STATUS_PENDING))
        .values(
            crawler_status=CRAWLER_STATUS_ONLINE,
            online_date=today,
            version=Source.version + 1,
            updated_at=now,
            updated_by_id=actor.id,
            updated_by_name=actor.name,
        )
        .returning(Source.site_code)
        .execution_options(synchronize_session=False)
    )
    return sorted(result.scalars())


async def count_known(session: AsyncSession, codes: set[str]) -> int:
    if not codes:
        return 0
    return int(await session.scalar(select(func.count()).where(Source.site_code.in_(codes))) or 0)
