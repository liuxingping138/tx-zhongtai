"""受控重放 Outbox。默认只重放 dead/failed，不引入额外消息队列。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from app.core.database import SessionLocal
from app.domain.enums import OutboxStatus
from app.repositories import outbox as outbox_repo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iam.cli.outbox_replay")


async def main() -> None:
    parser = argparse.ArgumentParser(description="重放 Outbox 待处理事件")
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--status", default="dead,failed", help="逗号分隔：dead,failed")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    statuses = tuple(item.strip() for item in args.status.split(",") if item.strip())
    allowed = {OutboxStatus.DEAD, OutboxStatus.FAILED, OutboxStatus.PENDING, OutboxStatus.DELIVERING}
    if not statuses or any(item not in allowed for item in statuses):
        raise SystemExit("status 只能是 dead/failed/pending/delivering")
    event_id = uuid.UUID(args.event_id) if args.event_id else None
    async with SessionLocal() as session:
        count = await outbox_repo.replay(
            session,
            event_id=event_id,
            event_type=args.event_type,
            statuses=statuses,
            limit=args.limit,
        )
        await session.commit()
    logger.info("outbox_replayed count=%s", count)


if __name__ == "__main__":
    asyncio.run(main())
