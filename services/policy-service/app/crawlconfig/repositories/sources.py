"""按规则表的网站编码和配置日期改信源的爬虫状态、上线时间。"""

from __future__ import annotations

from datetime import date, datetime

from platform_common.actors import Actor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.domain.fields import CRAWLER_STATUS_ONLINE, CRAWLER_STATUS_PENDING
from app.policy.domain.models import Source


async def apply_rule_dates(
    session: AsyncSession, first_dates: dict[str, date], *, now: datetime, actor: Actor, placeholder: str = ""
) -> tuple[list[str], list[str]]:
    """规则表里有的网站：未爬、没填状态的改成已爬；已爬的上线时间对齐成规则创建日期。异常和其他人工状态不动。

    同步第一次见到这个网站的规则（rule_date 为空）时早晚都对齐：导入时直接标已爬、上线时间随手填的
    （如一批填成 2024-10-01）、上线时给历史已爬统一补填的 placeholder，都不是真的配置日。
    见过之后只往前挪、不往后挪：网站最早那条规则被删（改版重配）后，最早日期会变晚，跟着往后挪的话
    这个网站会从已经汇报过的那一周消失、又被算成新一周的新增，周报数字前后对不上（用户定的口径）。

    返回（新标已爬的网站编码，只改了上线时间的网站编码）。按主键排序加锁，和人工编辑互斥。
    """

    if not first_dates:
        return [], []
    statuses = (*CRAWLER_STATUS_PENDING, CRAWLER_STATUS_ONLINE)
    rows = (
        await session.scalars(
            select(Source)
            .where(Source.site_code.in_(first_dates), Source.crawler_status.in_(statuses))
            .order_by(Source.id)
            .with_for_update()
        )
    ).all()
    marked: list[str] = []
    redated: list[str] = []
    for row in rows:
        target = first_dates[row.site_code].isoformat()
        seen = row.rule_date
        # 记下见过的最早规则日期：只记不改版本号，页面上的编辑不会因为它撞版本。
        row.rule_date = min(seen, target) if seen else target
        if row.crawler_status == CRAWLER_STATUS_ONLINE:
            # 上线时间是 YYYY-MM-DD 文本，字符串比较就是日期先后；空的（历史补填前）照常填上。
            ruled = seen and row.online_date and row.online_date != placeholder
            if row.online_date == target or (ruled and row.online_date < target):
                continue
            redated.append(row.site_code)
        else:
            row.crawler_status = CRAWLER_STATUS_ONLINE
            marked.append(row.site_code)
        row.online_date = target
        row.version += 1
        row.updated_at = now
        row.updated_by_id, row.updated_by_name = actor.id, actor.name
    return sorted(marked), sorted(redated)


async def count_known(session: AsyncSession, codes: set[str]) -> int:
    if not codes:
        return 0
    return int(await session.scalar(select(func.count()).where(Source.site_code.in_(codes))) or 0)
