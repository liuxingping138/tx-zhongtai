"""信源的爬虫状态与上线时间：改成「已爬」记当天上线，以及勾选多条批量改状态。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.policy.domain.fields import CRAWLER_STATUS_ONLINE as ONLINE_STATUS
from app.policy.repositories import sources as repo

# 审计里最多记这么多个网站编码，和接口单次勾选上限一致。
BATCH_STATUS_MAX = 500


def online_date_after(old_status: str, new_status: str, old_date: str, new_date: str, today: str) -> str:
    """爬虫状态从别的值变成「已爬」时，上线时间记为当天（北京日期）。

    同一次保存里手动改了上线时间的，以手填为准，方便补录和纠错；停爬（已爬改成别的）不动上线时间。
    新建时 old_status、old_date 都是空串，选了「已爬」又没填日期也记当天。
    """

    if new_status == ONLINE_STATUS and old_status != ONLINE_STATUS and new_date == old_date:
        return today
    return new_date


def beijing_today() -> str:
    return datetime.now(BEIJING).date().isoformat()


async def set_crawler_status(
    session: AsyncSession, actor: Actor, item_ids: list[uuid.UUID], status: str
) -> dict[str, Any]:
    """勾选多条批量改爬虫状态。上线时间按 online_date_after 的规则跟着变；状态本来就一样的不算修改。"""

    status = status.strip()
    if not status:
        raise ApiError("爬虫状态不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    rows = await repo.get_many_for_update(session, item_ids)
    if len(rows) != len(set(item_ids)):
        raise NotFoundError("部分信源已不存在，请刷新后重试")
    today, now = beijing_today(), utcnow()
    changed = []
    for row in rows:
        if row.crawler_status == status:
            continue
        row.online_date = online_date_after(row.crawler_status, status, row.online_date, row.online_date, today)
        row.crawler_status = status
        row.version += 1
        row.updated_at = now
        row.updated_by_id = actor.id
        row.updated_by_name = actor.name
        changed.append(row)
    if changed:
        await enqueue_event(
            session,
            event_type="policy.source.status_changed",
            actor=actor,
            target_id=str(changed[0].id) if len(changed) == 1 else "batch",
            changes={"crawler_status": status, "rows": len(changed)},
            extra={"site_codes": [row.site_code for row in changed][:BATCH_STATUS_MAX]},
        )
    return {"updated": len(changed), "unchanged": len(rows) - len(changed)}
