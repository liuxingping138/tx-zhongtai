"""需要独立于业务事务落库的审计事件。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.database import SessionLocal
from app.repositories import outbox as outbox_repo


async def enqueue_independent(
    *,
    event_type: str,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> None:
    """失败、拒绝类事件用独立事务提交：业务随后回滚时，这条审计也要留下。"""

    async with SessionLocal() as session:
        await outbox_repo.enqueue(
            session,
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            schema_version=schema_version,
        )
        await session.commit()
