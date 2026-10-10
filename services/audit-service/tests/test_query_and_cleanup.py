"""审计查询过滤、写入去重、查询时间口径和到期清理。不连数据库：SQL 编译出来检查，会话用替身。"""

from __future__ import annotations

import os

os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://audit_app:test@localhost:5432/audit_db")

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.clock import BEIJING
from platform_common.errors import ApiError
from sqlalchemy import Select, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.application import cleanup, ingest, query
from app.application.schemas import IngestRequest
from app.domain.models import AuditEvent
from app.repositories import events as event_repo


def sql(stmt: Select[Any]) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def body(**overrides: Any) -> IngestRequest:
    fields: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "occurred_at": datetime(2026, 10, 1, tzinfo=UTC),
        "actor_name_snapshot": "张三",
        "module_code": "policy.sources",
        "action_code": "create",
        "outcome": "success",
    }
    return IngestRequest(**(fields | overrides))


class TestApplyFilters:
    def test_no_conditions_adds_no_where(self) -> None:
        assert "WHERE" not in sql(event_repo.apply_filters(select(AuditEvent), actor_name=[], module_code=""))

    def test_time_range_is_half_open(self) -> None:
        start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
        text = sql(event_repo.apply_filters(select(AuditEvent), occurred_from=start, occurred_to=end))
        assert "occurred_at >= '2026-10-01" in text
        assert "occurred_at < '2026-10-02" in text

    def test_multi_select_uses_in_and_fields_are_anded(self) -> None:
        text = sql(event_repo.apply_filters(select(AuditEvent), module_code=["a", "b"], outcome="failed"))
        assert "module_code IN ('a', 'b')" in text
        assert "outcome IN ('failed')" in text
        assert " AND " in text

    def test_actor_name_is_fuzzy_and_escapes_wildcards(self) -> None:
        stmt = event_repo.apply_filters(select(AuditEvent), actor_name=["张%三", "李_四"])
        patterns = set(stmt.compile(dialect=postgresql.dialect()).params.values())
        assert {"%张\\%三%", "%李\\_四%"} <= patterns
        assert " OR " in sql(stmt)


class _Session:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.added: list[Any] = []
        self.commit = AsyncMock(side_effect=commit_error)
        self.rollback = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)


class TestIngest:
    async def test_new_event_is_stored(self) -> None:
        session = _Session()
        event = body()
        result = await ingest.ingest_event(session, source_service="policy-service", body=event, max_bytes=65536)  # type: ignore[arg-type]
        assert result.event_id == event.event_id
        assert result.duplicate is False
        assert len(session.added) == 1

    async def test_redelivered_event_is_reported_as_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        event = body()
        session = _Session(commit_error=IntegrityError("insert", {}, Exception("unique")))
        monkeypatch.setattr(event_repo, "get_event", AsyncMock(return_value=SimpleNamespace(event_id=event.event_id)))
        result = await ingest.ingest_event(session, source_service="policy-service", body=event, max_bytes=65536)  # type: ignore[arg-type]
        assert result.duplicate is True
        session.rollback.assert_awaited_once()

    async def test_conflict_without_existing_row_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _Session(commit_error=IntegrityError("insert", {}, Exception("other")))
        monkeypatch.setattr(event_repo, "get_event", AsyncMock(return_value=None))
        with pytest.raises(IntegrityError):
            await ingest.ingest_event(session, source_service="policy-service", body=body(), max_bytes=65536)  # type: ignore[arg-type]

    async def test_oversized_event_is_rejected(self) -> None:
        with pytest.raises(ApiError, match="超过允许大小"):
            await ingest.ingest_event(_Session(), source_service="x", body=body(summary="长" * 1000), max_bytes=100)  # type: ignore[arg-type]


class TestQuery:
    async def test_naive_times_from_page_are_beijing_and_offset_follows_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        count = AsyncMock(return_value=0)
        rows = AsyncMock(return_value=[])
        monkeypatch.setattr(event_repo, "count_events", count)
        monkeypatch.setattr(event_repo, "list_events", rows)
        items, total = await query.list_page(
            AsyncMock(),
            page=3,
            page_size=20,
            occurred_from=datetime(2026, 10, 1, 8, 0),
            occurred_to=None,
            actor_id=None,
            actor_name=None,
            module_code=None,
            action_code=None,
            outcome=None,
        )
        assert (items, total) == ([], 0)
        assert count.await_args is not None
        assert count.await_args.kwargs["occurred_from"] == datetime(2026, 10, 1, 8, 0, tzinfo=BEIJING)
        assert rows.await_args is not None
        assert rows.await_args.kwargs["offset"] == 40
        assert rows.await_args.kwargs["limit"] == 20


class TestCleanup:
    async def test_deletes_rows_older_than_retention_and_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = datetime(2026, 10, 10, tzinfo=UTC)
        monkeypatch.setattr(cleanup, "utcnow", lambda: now)
        executed: list[Any] = []

        async def execute(stmt: Any) -> Any:
            executed.append(stmt)
            return SimpleNamespace(all=lambda: [1, 2, 3])

        session = SimpleNamespace(execute=execute, commit=AsyncMock())
        deleted = await cleanup.delete_expired(session, retention_days=180)  # type: ignore[arg-type]
        assert deleted == 3
        session.commit.assert_awaited_once()
        cutoff = (now - timedelta(days=180)).isoformat(sep=" ")
        assert f"occurred_at < '{cutoff}" in str(
            executed[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )

    async def test_records_a_cleanup_audit_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded = AsyncMock()
        monkeypatch.setattr(cleanup, "ingest_event", recorded)
        await cleanup.record_cleanup(AsyncMock(), deleted=7, retention_days=180, max_bytes=65536)
        assert recorded.await_args is not None
        sent: IngestRequest = recorded.await_args.kwargs["body"]
        assert (sent.module_code, sent.action_code) == ("system.audit", "cleanup")
        assert sent.changes == {"deleted": 7, "retention_days": 180}
