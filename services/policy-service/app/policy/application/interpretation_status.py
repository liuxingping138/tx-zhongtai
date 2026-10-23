"""政策解读勾选多条批量改数据状态：AI 写的行都是「待验证」，人工核对后一次改成「人工验证」。

改成人工验证的行，AI 重新解读、回填市场机会都不再覆盖；新增场景也要人工验证过才能同步进码表。
"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.policy.domain.fields import DATA_STATUS_CHOICES
from app.policy.repositories import interpretations as repo

BATCH_MAX = 500


async def set_data_status(
    session: AsyncSession, actor: Actor, item_ids: list[uuid.UUID], status: str
) -> dict[str, Any]:
    if status not in DATA_STATUS_CHOICES:
        raise ApiError(
            f"数据状态只能是{'、'.join(DATA_STATUS_CHOICES)}", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    rows = await repo.get_many_for_update(session, item_ids)
    if len(rows) != len(set(item_ids)):
        raise NotFoundError("部分解读已不存在，请刷新后重试")
    now = utcnow()
    changed = [row for row in rows if row.data_status != status]
    for row in changed:
        row.data_status = status
        row.version += 1
        row.updated_at = now
        row.updated_by_id = actor.id
        row.updated_by_name = actor.name
    if changed:
        await enqueue_event(
            session,
            event_type="policy.interpretation.status_changed",
            actor=actor,
            target_id=str(changed[0].id) if len(changed) == 1 else "batch",
            changes={"data_status": status, "rows": len(changed)},
            extra={"record_ids": [row.record_id for row in changed][:BATCH_MAX]},
        )
    return {"updated": len(changed), "unchanged": len(rows) - len(changed)}
