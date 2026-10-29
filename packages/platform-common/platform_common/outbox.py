"""Outbox 事件的跨服务数据结构与仓储。具体业务事件类型仍由各服务定义。

投递按「认领 → 投递 → 按租约回写」三步走，与 iam-service 的 Worker 同一套语义：

- 认领时置为 delivering 并写租约截止时间，先提交再投递，投递期间不占着行锁。
- 进程在投递途中重启、或本地抛了异常，租约到期后这些事件会被重新认领，不会永远卡在 delivering。
- 回写带租约条件：租约已被别人重新认领时本次回写不生效，避免旧进程覆盖新结果。
  审计服务按 event_id 去重，重复投递不会产生重复记录。
"""

from __future__ import annotations

import argparse
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy import CursorResult, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_common.clock import utcnow
from platform_common.enums import OutboxStatus

# 一批最多 20 条、每条投递超时 5 秒，最坏 100 秒投完；租约留足余量。
DEFAULT_LEASE = timedelta(minutes=5)
REPLAYABLE_STATUSES = (OutboxStatus.DEAD, OutboxStatus.FAILED, OutboxStatus.PENDING, OutboxStatus.DELIVERING)


class OutboxEventDraft(BaseModel):
    event_type: str
    payload: dict[str, Any]
    schema_version: int = Field(default=1, ge=1)


# 退避最长 15 分钟。配合各服务 worker_max_attempts=100，审计服务连不上、密钥对不上能容忍约一天才置 dead；
# 原来最长 60 秒、8 次，三分钟就放弃，审计服务起不来一会儿，四个服务的审计就全进 dead。
RETRY_DELAY_CAP_SECONDS = 900


def retry_delay(attempts: int) -> timedelta:
    """指数退避，最长 15 分钟。"""

    return timedelta(seconds=min(2**attempts, RETRY_DELAY_CAP_SECONDS))


class OutboxRepository:
    """Outbox 表的读写。

    各服务的 outbox 表结构一致、只是表名不同（policy_outbox / codebook_outbox），
    所以这里按 ORM model 参数化，逻辑只留一份。
    """

    def __init__(self, model: type[Any]) -> None:
        self._model = model

    async def enqueue(self, session: AsyncSession, *, event_type: str, payload: dict[str, Any]) -> Any:
        event = self._model(
            event_id=uuid.uuid4(),
            event_type=event_type,
            schema_version=1,
            payload=payload,
            status=OutboxStatus.PENDING,
            attempts=0,
            created_at=utcnow(),
        )
        session.add(event)
        return event

    async def claim_pending(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
        lease: timedelta = DEFAULT_LEASE,
        now: datetime | None = None,
    ) -> list[Any]:
        model = self._model
        current = now or utcnow()
        due = and_(
            model.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
            or_(model.next_retry_at.is_(None), model.next_retry_at <= current),
        )
        # 租约为空的 delivering 是加租约之前卡住的存量事件，同样视为已过期。
        abandoned = and_(
            model.status == OutboxStatus.DELIVERING,
            or_(model.lease_until.is_(None), model.lease_until < current),
        )
        result = await session.execute(
            select(model)
            .where(or_(due, abandoned))
            .order_by(model.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars())
        lease_until = current + lease
        for event in events:
            event.status = OutboxStatus.DELIVERING
            event.lease_until = lease_until
            event.attempts += 1
        return events

    async def _update_if_leased(
        self, session: AsyncSession, event_id: Any, expected_lease: datetime, values: dict[str, Any]
    ) -> bool:
        model = self._model
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(model)
                .where(
                    model.event_id == event_id,
                    model.status == OutboxStatus.DELIVERING,
                    model.lease_until == expected_lease,
                )
                .values(**values)
            ),
        )
        return bool(result.rowcount)

    async def mark_delivered(self, session: AsyncSession, event_id: Any, expected_lease: datetime) -> bool:
        """返回 False 表示租约已被重新认领，本次结果作废。"""

        return await self._update_if_leased(
            session,
            event_id,
            expected_lease,
            {"status": OutboxStatus.DELIVERED, "error_message": None, "next_retry_at": None, "lease_until": None},
        )

    async def mark_retry(
        self,
        session: AsyncSession,
        event_id: Any,
        expected_lease: datetime,
        *,
        attempts: int,
        error: str,
        max_attempts: int,
    ) -> bool:
        """失败回写：未到上限置 failed 并退避，到上限置 dead。返回 False 表示租约已失效。"""

        dead = attempts >= max_attempts
        return await self._update_if_leased(
            session,
            event_id,
            expected_lease,
            {
                "status": OutboxStatus.DEAD if dead else OutboxStatus.FAILED,
                "error_message": error[:500],
                "next_retry_at": None if dead else utcnow() + retry_delay(attempts),
                "lease_until": None,
            },
        )

    async def replay(
        self,
        session: AsyncSession,
        *,
        statuses: Sequence[str] = (OutboxStatus.DEAD, OutboxStatus.FAILED),
        event_id: uuid.UUID | None = None,
        event_type: str | None = None,
        limit: int = 200,
    ) -> int:
        """把选中的事件重置为待投递，重试计数清零。"""

        model = self._model
        stmt = select(model).where(model.status.in_(tuple(statuses))).order_by(model.created_at).limit(limit)
        if event_id is not None:
            stmt = stmt.where(model.event_id == event_id)
        if event_type:
            stmt = stmt.where(model.event_type == event_type)
        rows = list((await session.execute(stmt.with_for_update(skip_locked=True))).scalars())
        now = utcnow()
        for event in rows:
            event.status = OutboxStatus.PENDING
            event.next_retry_at = now
            event.lease_until = None
            event.attempts = 0
            event.error_message = None
        return len(rows)


async def run_replay_cli(
    session_factory: async_sessionmaker[AsyncSession],
    repository: OutboxRepository,
    *,
    service: str,
    argv: Sequence[str] | None = None,
) -> int:
    """各业务服务 `python -m app.cli.outbox_replay` 的共用入口，参数与 iam-service 的重放 CLI 一致。"""

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(f"{service}.cli.outbox_replay")
    parser = argparse.ArgumentParser(description=f"重放 {service} 的 Outbox 事件")
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--status", default="dead,failed", help="逗号分隔：dead,failed,pending,delivering")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    statuses = tuple(item.strip() for item in args.status.split(",") if item.strip())
    if not statuses or any(item not in REPLAYABLE_STATUSES for item in statuses):
        parser.error("status 只能是 dead/failed/pending/delivering")
    async with session_factory() as session:
        count = await repository.replay(
            session,
            statuses=statuses,
            event_id=uuid.UUID(args.event_id) if args.event_id else None,
            event_type=args.event_type,
            limit=args.limit,
        )
        await session.commit()
    logger.info("outbox_replayed service=%s count=%s", service, count)
    return count
