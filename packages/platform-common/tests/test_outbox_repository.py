"""公共 Outbox 仓储：认领带租约、按租约回写、失败退避到封存、受控重放与命令行参数校验。会话用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase

from platform_common.enums import OutboxStatus
from platform_common.outbox import (
    DEFAULT_LEASE,
    OutboxRepository,
    retry_delay,
    run_replay_cli,
)

NOW = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)


class _Base(DeclarativeBase):
    pass


class _Event(_Base):
    """只要有仓储用到的列即可；真正的表在各服务里。"""

    __tablename__ = "fake_outbox"
    event_id = Column(String, primary_key=True)
    event_type = Column(String)
    schema_version = Column(Integer)
    payload = Column(String)
    status = Column(String)
    attempts = Column(Integer)
    created_at = Column(DateTime(timezone=True))
    next_retry_at = Column(DateTime(timezone=True))
    lease_until = Column(DateTime(timezone=True))
    error_message = Column(String)


def _event(**overrides: Any) -> SimpleNamespace:
    base = {
        "status": OutboxStatus.PENDING,
        "attempts": 0,
        "lease_until": None,
        "next_retry_at": None,
        "error_message": "x",
    }
    return SimpleNamespace(**(base | overrides))


class _Session:
    def __init__(self, events: list[Any] | None = None, rowcount: int = 1) -> None:
        self.events = events or []
        self.added: list[Any] = []
        self.executed: list[Any] = []
        self.rowcount = rowcount

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def execute(self, statement: Any) -> Any:
        self.executed.append(statement)
        return SimpleNamespace(scalars=lambda: iter(self.events), rowcount=self.rowcount)


def test_backoff_doubles_and_caps_at_a_minute() -> None:
    assert [retry_delay(n).total_seconds() for n in (1, 2, 3, 5, 6, 10)] == [2, 4, 8, 32, 60, 60]


class TestEnqueue:
    async def test_new_events_start_pending_with_no_attempts(self) -> None:
        session = _Session()
        event = await OutboxRepository(_Event).enqueue(session, event_type="x.created", payload={"a": 1})  # type: ignore[arg-type]
        assert session.added == [event]
        assert (event.status, event.attempts, event.schema_version) == (OutboxStatus.PENDING, 0, 1)
        assert isinstance(event.event_id, uuid.UUID)


class TestClaim:
    async def test_claimed_events_get_a_lease_and_an_attempt(self) -> None:
        events = [_event(), _event(attempts=2)]
        claimed = await OutboxRepository(_Event).claim_pending(_Session(events), now=NOW)  # type: ignore[arg-type]
        assert [e.attempts for e in claimed] == [1, 3]
        assert all(e.status == OutboxStatus.DELIVERING and e.lease_until == NOW + DEFAULT_LEASE for e in claimed)

    async def test_the_query_skips_locked_rows_and_honours_the_limit(self) -> None:
        session = _Session()
        await OutboxRepository(_Event).claim_pending(session, limit=7, now=NOW)  # type: ignore[arg-type]
        sql = str(session.executed[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "SKIP LOCKED" in sql and "LIMIT 7" in sql
        assert "lease_until IS NULL" in sql  # 加租约之前卡住的存量事件也要被接回


class TestLeasedWriteBack:
    async def test_delivered_only_counts_when_the_lease_still_matches(self) -> None:
        repo = OutboxRepository(_Event)
        assert await repo.mark_delivered(_Session(rowcount=1), "e1", NOW) is True  # type: ignore[arg-type]
        assert await repo.mark_delivered(_Session(rowcount=0), "e1", NOW) is False  # type: ignore[arg-type]

    async def test_failure_backs_off_until_the_attempt_budget_is_spent(self) -> None:
        repo = OutboxRepository(_Event)
        retry = _Session()
        await repo.mark_retry(retry, "e1", NOW, attempts=2, error="x" * 900, max_attempts=3)  # type: ignore[arg-type]
        dead = _Session()
        await repo.mark_retry(dead, "e1", NOW, attempts=3, error="boom", max_attempts=3)  # type: ignore[arg-type]
        retry_values = retry.executed[0].compile().params
        dead_values = dead.executed[0].compile().params
        assert retry_values["status"] == OutboxStatus.FAILED and retry_values["next_retry_at"] is not None
        assert len(retry_values["error_message"]) == 500
        assert dead_values["status"] == OutboxStatus.DEAD and dead_values["next_retry_at"] is None


class TestReplay:
    async def test_replayed_events_are_reset_to_pending(self) -> None:
        events = [_event(status=OutboxStatus.DEAD, attempts=8, error_message="boom", lease_until=NOW)]
        count = await OutboxRepository(_Event).replay(_Session(events))  # type: ignore[arg-type]
        assert count == 1
        e = events[0]
        assert (e.status, e.attempts, e.lease_until, e.error_message) == (OutboxStatus.PENDING, 0, None, None)

    async def test_filters_by_id_and_type_are_applied(self) -> None:
        session = _Session()
        await OutboxRepository(_Event).replay(session, event_id=uuid.uuid4(), event_type="x.created")  # type: ignore[arg-type]
        sql = str(session.executed[0].compile())
        assert "event_id" in sql and "event_type" in sql


class _Factory:
    def __init__(self, session: Any) -> None:
        self.session = session

    def __call__(self) -> _Factory:
        return self

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class TestReplayCli:
    async def test_defaults_replay_dead_and_failed_and_commit(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        repository = MagicMock()
        repository.replay = AsyncMock(return_value=4)
        count = await run_replay_cli(_Factory(session), repository, service="policy", argv=[])  # type: ignore[arg-type]
        assert count == 4
        assert repository.replay.await_args.kwargs["statuses"] == (OutboxStatus.DEAD, OutboxStatus.FAILED)
        session.commit.assert_awaited_once()

    async def test_unknown_status_is_rejected_before_touching_the_database(self) -> None:
        repository = MagicMock()
        repository.replay = AsyncMock()
        with pytest.raises(SystemExit):
            await run_replay_cli(
                _Factory(SimpleNamespace()), repository, service="policy", argv=["--status", "delivered"]
            )  # type: ignore[arg-type]
        repository.replay.assert_not_awaited()

    async def test_event_id_and_limit_are_passed_through(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        repository = MagicMock()
        repository.replay = AsyncMock(return_value=1)
        target = uuid.uuid4()
        await run_replay_cli(
            _Factory(session),
            repository,
            service="policy",  # type: ignore[arg-type]
            argv=["--event-id", str(target), "--limit", "5", "--status", "pending"],
        )
        kwargs = repository.replay.await_args.kwargs
        assert (kwargs["event_id"], kwargs["limit"], kwargs["statuses"]) == (target, 5, ("pending",))
