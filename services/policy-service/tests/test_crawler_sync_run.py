"""爬虫监测同步的执行流程：按天写入、成功/失败/修复三种收尾，以及源库读取的 SQL 参数。数据库与源库用替身。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.crawler.application import crawler_sync as sync

TODAY = date(2026, 10, 10)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.execute = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)

    @property
    def run_row(self) -> Any:
        return self.added[0]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        targets=[date(2026, 10, 10), date(2026, 10, 9)], mark=datetime(2026, 10, 10, tzinfo=UTC), written=[]
    )

    async def replace_day(_s: object, day: date, rows: list[Any]) -> int:
        state.written.append((day, len(rows)))
        return len(rows)

    monkeypatch.setattr(sync, "plan", AsyncMock(side_effect=lambda *_a, **_k: (state.targets, state.mark)))
    monkeypatch.setattr(sync, "fetch_day", MagicMock(return_value=[{"site_name": "甲"}]))
    monkeypatch.setattr(sync, "replace_day", replace_day)
    monkeypatch.setattr(sync, "rebuild_sites", AsyncMock(return_value=42))
    state.refresh_history = AsyncMock()
    monkeypatch.setattr(sync.status_history, "refresh_history", state.refresh_history)
    return state


class TestSync:
    async def test_incremental_success_writes_each_day_and_records_the_watermark(self, env: SimpleNamespace) -> None:
        session = _Session()
        await sync._sync(session, sync.SyncWindow(mode=sync.MODE_INCREMENTAL))  # type: ignore[arg-type]
        run = session.run_row
        assert env.written == [(date(2026, 10, 10), 1), (date(2026, 10, 9), 1)]
        assert (run.status, run.days_synced, run.site_rows, run.watermark) == ("success", 2, 42, env.mark)
        assert (run.date_from, run.date_to) == (date(2026, 10, 9), date(2026, 10, 10))
        assert run.finished_at is not None

    async def test_repair_never_records_a_watermark(self, env: SimpleNamespace) -> None:
        session = _Session()
        await sync._sync(session, sync.SyncWindow(mode=sync.MODE_REPAIR, days=2))  # type: ignore[arg-type]
        assert session.run_row.status == "success" and session.run_row.watermark is None

    async def test_backfill_records_the_mark_up_front_so_a_resume_can_reuse_it(self, env: SimpleNamespace) -> None:
        session = _Session()
        seen: list[Any] = []
        session.commit.side_effect = lambda: seen.append(session.run_row.watermark)
        await sync._sync(session, sync.SyncWindow(mode=sync.MODE_BACKFILL))  # type: ignore[arg-type]
        assert seen[1] == env.mark  # 规划后的第一次提交就带着水位，早于第一天的写入

    async def test_failure_is_recorded_and_re_raised(self, env: SimpleNamespace) -> None:
        env.targets = [TODAY]
        sync.fetch_day.side_effect = OSError("source offline")  # type: ignore[attr-defined]
        session = _Session()
        with pytest.raises(OSError):
            await sync._sync(session, sync.SyncWindow(mode=sync.MODE_INCREMENTAL))  # type: ignore[arg-type]
        run = session.run_row
        assert run.status == "failed" and run.error_message == "source offline" and run.finished_at is not None
        session.rollback.assert_awaited_once()

    async def test_nothing_to_sync_still_rebuilds_and_succeeds(self, env: SimpleNamespace) -> None:
        env.targets = []
        session = _Session()
        await sync._sync(session, sync.SyncWindow(mode=sync.MODE_INCREMENTAL))  # type: ignore[arg-type]
        assert session.run_row.date_from is None and session.run_row.status == "success"

    async def test_success_records_todays_status_for_week_comparison(self, env: SimpleNamespace) -> None:
        session = _Session()
        await sync._sync(session, sync.SyncWindow(mode=sync.MODE_INCREMENTAL))  # type: ignore[arg-type]
        env.refresh_history.assert_awaited_once()
        assert env.refresh_history.await_args.args[1] == datetime.now(sync.BEIJING).date()


class TestReplaceDay:
    async def test_empty_day_only_clears_the_old_rows(self) -> None:
        session = _Session()
        assert await sync.replace_day(session, TODAY, []) == 0  # type: ignore[arg-type]
        assert session.execute.await_count == 1

    async def test_large_days_are_written_in_chunks_of_a_thousand(self) -> None:
        session = _Session()
        rows = [
            {
                "collect_date": TODAY,
                "site_name": str(i),
                "province_name": "",
                "city_name": "",
                "row_count": 1,
                "last_created_at": None,
                "last_published_date": None,
            }
            for i in range(2500)
        ]
        assert await sync.replace_day(session, TODAY, rows) == 2500  # type: ignore[arg-type]
        assert session.execute.await_count == 1 + 3


class TestRebuild:
    async def test_thresholds_come_from_settings_and_count_is_returned(self) -> None:
        session = _Session()
        session.execute.side_effect = [None, SimpleNamespace(rowcount=7)]
        assert await sync.rebuild_sites(session) == 7  # type: ignore[arg-type]
        params = session.execute.await_args.args[1]
        assert params == {"normal_days": 7, "watch_days": 30}


class TestRun:
    async def test_a_second_sync_is_refused_while_the_lock_is_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Conn:
            scalar = AsyncMock(return_value=False)
            commit = AsyncMock()

            async def __aenter__(self) -> Conn:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

        monkeypatch.setattr(sync, "engine", SimpleNamespace(connect=Conn))
        with pytest.raises(RuntimeError, match="已有爬虫监测同步"):
            await sync.run(mode=sync.MODE_INCREMENTAL)


class _FakeMysql:
    """爬虫库连接的替身：记录执行过的 SQL 与参数，按预设返回行。只验证参数顺序，不验证 MySQL 方言。"""

    def __init__(self, rows: list[dict[str, Any]], one: list[dict[str, Any]] | None = None) -> None:
        self.rows, self.one, self.executed = rows, list(one or []), []

    @contextmanager
    def connect(self):  # type: ignore[no-untyped-def]
        outer = self

        class Cursor:
            def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
                outer.executed.append((sql, params))

            def fetchall(self) -> list[dict[str, Any]]:
                return outer.rows

            def fetchone(self) -> dict[str, Any]:
                return outer.one.pop(0)

        @contextmanager
        def cursor():  # type: ignore[no-untyped-def]
            yield Cursor()

        yield SimpleNamespace(cursor=cursor)


class TestSourceReads:
    def test_fetch_day_binds_today_then_the_day_and_merges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMysql(
            [
                {
                    "site_name": "甲",
                    "province_name": "",
                    "city_name": "",
                    "row_count": 3,
                    "last_created": datetime(2026, 10, 9, 8, 0),
                    "last_published": "2026-10-08",
                }
            ]
        )
        monkeypatch.setattr(sync, "mysql_connect", fake.connect)
        rows = sync.fetch_day(date(2026, 10, 9), TODAY)
        assert fake.executed[0][1] == ("2026-10-10", "2026-10-09")
        assert rows[0]["row_count"] == 3 and rows[0]["last_published_date"] == date(2026, 10, 8)
        assert "<> '-1'" in fake.executed[0][0]

    def test_affected_days_returns_days_and_the_latest_created_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMysql(
            [
                {"collect_date": date(2026, 10, 9), "max_created": datetime(2026, 10, 9, 8, 0)},
                {"collect_date": date(2026, 10, 10), "max_created": datetime(2026, 10, 10, 9, 0)},
                {"collect_date": None, "max_created": None},
            ]
        )
        monkeypatch.setattr(sync, "mysql_connect", fake.connect)
        days, mark = sync.fetch_affected_days(datetime(2026, 10, 9, tzinfo=UTC))
        assert days == {
            date(2026, 10, 9): datetime(2026, 10, 9, 0, 0, tzinfo=UTC),
            date(2026, 10, 10): datetime(2026, 10, 10, 1, 0, tzinfo=UTC),
        }
        assert mark == datetime(2026, 10, 10, 1, 0, tzinfo=UTC)
        assert fake.executed[0][1] == ("2026-10-09 08:00:00",)

    def test_affected_days_with_no_new_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sync, "mysql_connect", _FakeMysql([]).connect)
        assert sync.fetch_affected_days(datetime(2026, 10, 9, tzinfo=UTC)) == ({}, None)

    def test_source_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMysql([], one=[{"first_day": date(2023, 10, 18)}, {"max_created": datetime(2026, 10, 10, 8, 0)}])
        monkeypatch.setattr(sync, "mysql_connect", fake.connect)
        assert sync.fetch_source_bounds() == (date(2023, 10, 18), datetime(2026, 10, 10, 0, 0, tzinfo=UTC))

    def test_source_bounds_of_an_empty_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMysql([], one=[{"first_day": None}, {"max_created": None}])
        monkeypatch.setattr(sync, "mysql_connect", fake.connect)
        assert sync.fetch_source_bounds() == (None, None)
