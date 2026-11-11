"""审计查询过滤、写入去重、查询时间口径和到期清理。不连数据库：SQL 编译出来检查，会话用替身。"""

from __future__ import annotations

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
from app.domain.filters import EventFilters
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
        assert "WHERE" not in sql(
            event_repo.apply_filters(select(AuditEvent), EventFilters(actor_name=[], module_code=""))
        )

    def test_time_range_is_half_open(self) -> None:
        start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
        text = sql(event_repo.apply_filters(select(AuditEvent), EventFilters(occurred_from=start, occurred_to=end)))
        assert "occurred_at >= '2026-10-01" in text
        assert "occurred_at < '2026-10-02" in text

    def test_multi_select_uses_in_and_fields_are_anded(self) -> None:
        text = sql(event_repo.apply_filters(select(AuditEvent), EventFilters(module_code=["a", "b"], outcome="failed")))
        assert "module_code IN ('a', 'b')" in text
        assert "outcome IN ('failed')" in text
        assert " AND " in text

    def test_actor_name_is_fuzzy_and_escapes_wildcards(self) -> None:
        stmt = event_repo.apply_filters(select(AuditEvent), EventFilters(actor_name=["张%三", "李_四"]))
        patterns = set(stmt.compile(dialect=postgresql.dialect()).params.values())
        assert {"%张\\%三%", "%李\\_四%"} <= patterns
        assert " OR " in sql(stmt)


class TestBusinessLine:
    def test_module_root_matches_the_root_and_its_children_only(self) -> None:
        stmt = event_repo.apply_filters(select(AuditEvent), EventFilters(module_root=["system", "auth"]))
        # 「system」本身和「system.」打头的都算，「systemx」这类不算；几个业务模块之间是「或」。
        params = set(stmt.compile(dialect=postgresql.dialect()).params.values())
        assert {"system", "system.%", "auth", "auth.%"} <= params
        assert " OR " in sql(stmt)

    def test_business_line_filter_uses_in(self) -> None:
        text = sql(event_repo.apply_filters(select(AuditEvent), EventFilters(business_line=["tender"])))
        assert "business_line IN ('tender')" in text

    def test_ingest_derives_the_business_line(self) -> None:
        def line(module: str, changes: dict[str, Any] | None = None) -> str | None:
            return ingest.build_event("x", body(module_code=module, changes=changes)).business_line

        assert line("policy.sources") == "policy"
        # AI 按事件里记的模板类型；没记的、乱写的为空。系统管理、码表管理不属于哪条业务线。
        assert line("ai.batch_runs", {"category": "tender"}) == "tender"
        assert line("ai.batch_runs", {"category": "x"}) is None
        assert line("ai.models") is None
        assert line("system.users") is None
        assert line("codebook.area_codes") is None


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
            AsyncMock(), EventFilters(occurred_from=datetime(2026, 10, 1, 8, 0)), page=3, page_size=20
        )
        assert (items, total) == ([], 0)
        assert count.await_args is not None
        assert count.await_args.args[1].occurred_from == datetime(2026, 10, 1, 8, 0, tzinfo=BEIJING)
        assert rows.await_args is not None
        assert rows.await_args.kwargs["offset"] == 40
        assert rows.await_args.kwargs["limit"] == 20

    @pytest.mark.parametrize(
        ("page", "got", "counted", "total"),
        [
            (1, 7, False, 7),  # 第一页没取满：总数就是这几条
            (3, 5, False, 45),  # 最后一页：前两页满的加这一页
            (1, 0, False, 0),  # 什么都没有
            (2, 20, True, 99),  # 取满了：后面可能还有，要数
            (5, 0, True, 99),  # 翻过了头：要数出真实总数，页面好退回去
        ],
    )
    async def test_count_only_when_the_page_does_not_tell_the_total(
        self, monkeypatch: pytest.MonkeyPatch, page: int, got: int, counted: bool, total: int
    ) -> None:
        count = AsyncMock(return_value=99)
        rows = [AuditEvent(**_row()) for _ in range(got)]
        monkeypatch.setattr(event_repo, "count_events", count)
        monkeypatch.setattr(event_repo, "list_events", AsyncMock(return_value=rows))
        items, result = await query.list_page(AsyncMock(), EventFilters(), page=page, page_size=20)
        assert len(items) == got
        assert result == total
        assert count.await_count == (1 if counted else 0)


def _row() -> dict[str, Any]:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    return {
        "id": uuid.uuid4(),
        "event_id": uuid.uuid4(),
        "occurred_at": now,
        "received_at": now,
        "source_service": "iam-service",
        "schema_version": 1,
        "outcome": "success",
    }


class TestOptions:
    """筛选项候选值沿索引逐个跳到下一个不同的值，不整表 DISTINCT；结果形状与公共的 preview_options 一致。"""

    def test_values_walk_the_index_instead_of_a_full_distinct(self) -> None:
        text = sql(event_repo.distinct_values_stmt(AuditEvent.actor_name_snapshot, keyword=None, limit=201))
        assert text.startswith("WITH RECURSIVE walk(value)")
        assert "DISTINCT" not in text
        assert "min(audit_events.actor_name_snapshot)" in text
        assert "actor_name_snapshot > ''" in text
        assert "actor_name_snapshot > walk.value" in text
        assert "ORDER BY walk.value" in text
        assert text.rstrip().endswith("LIMIT 201")

    def test_keyword_filters_the_walked_values(self) -> None:
        stmt = event_repo.distinct_values_stmt(AuditEvent.action_code, keyword=" 登_录 ", limit=50)
        assert "walk.value ILIKE" in sql(stmt)
        assert "%登\\_录%" in stmt.compile(dialect=postgresql.dialect()).params.values()

    async def test_preview_marks_truncation_like_the_shared_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        values = {
            "actor_name": [f"用户{i:03d}" for i in range(201)],
            "module_code": ["auth"],
            "action_code": [],
        }

        async def fake(_session: object, column: Any, *, keyword: str | None, limit: int) -> list[str]:
            field = next(name for name, col in event_repo.OPTION_COLUMNS.items() if col is column)
            assert keyword is None and limit == 201
            return values[field][:limit]

        monkeypatch.setattr(event_repo, "_distinct_values", fake)
        options = (await event_repo.list_options(AsyncMock()))["options"]
        assert options["actor_name"]["truncated"] is True and len(options["actor_name"]["items"]) == 200
        assert options["module_code"] == {"items": ["auth"], "truncated": False}
        assert options["action_code"] == {"items": [], "truncated": False}

    async def test_unknown_search_field_is_a_key_error(self) -> None:
        with pytest.raises(KeyError):
            await event_repo.search_option_values(AsyncMock(), field="summary", keyword="x")

    def test_option_columns_are_indexed(self) -> None:
        """每个候选值字段都要有以它打头的索引，否则「沿索引跳」每一步都是整表扫描，比原来还慢。"""

        leading = {index.columns[0].name for index in AuditEvent.__table__.indexes}
        assert {column.key for column in event_repo.OPTION_COLUMNS.values()} <= leading


class TestCleanup:
    async def test_deletes_rows_older_than_retention_and_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = datetime(2026, 10, 10, tzinfo=UTC)
        monkeypatch.setattr(cleanup, "utcnow", lambda: now)
        executed: list[Any] = []

        # 分批删：第一批满了接着删，不满就停。每批一个事务，不长时间占着表。
        counts = iter([cleanup.DELETE_BATCH, 3])

        async def execute(stmt: Any) -> Any:
            executed.append(stmt)
            return SimpleNamespace(rowcount=next(counts))

        session = SimpleNamespace(execute=execute, commit=AsyncMock())
        deleted = await cleanup.delete_expired(session, retention_days=180)  # type: ignore[arg-type]
        assert deleted == cleanup.DELETE_BATCH + 3
        assert session.commit.await_count == 2
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


class TestScheduledCleanup:
    async def test_refuses_without_a_separate_cleanup_account(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """应用账号对 audit_events 只有查和插；没配清理账号就明说，不拿应用账号去删。"""

        from platform_common.scheduler import UserFacingError

        from app.application import scheduled_jobs

        settings = SimpleNamespace(cleanup_database_url=None, database_url="postgresql+asyncpg://app@db/audit")
        monkeypatch.setattr(scheduled_jobs, "get_settings", lambda: settings)
        with pytest.raises(UserFacingError, match="清理账号"):
            await scheduled_jobs.run_cleanup(uuid.uuid4())
        settings.cleanup_database_url = settings.database_url
        with pytest.raises(UserFacingError, match="清理账号"):
            await scheduled_jobs.run_cleanup(uuid.uuid4())

    async def test_schedule_changes_are_written_straight_into_the_audit_table(self) -> None:
        from platform_common.actors import Actor

        from app.application import scheduled_jobs

        added: list[Any] = []
        session = SimpleNamespace(add=added.append)
        actor = Actor(id="u1", name="管理员")
        await scheduled_jobs.record_schedule_change(
            session,  # type: ignore[arg-type]
            event_type="scheduler.updated",
            actor=actor,
            target_id="audit_cleanup",
            changes={"daily_time": "05:00"},
        )
        event = added[0]
        assert (event.module_code, event.action_code, event.target_id) == (
            "system.scheduler",
            "update",
            "audit_cleanup",
        )
        assert event.changes == {"daily_time": "05:00"} and event.actor_name_snapshot == "管理员"
