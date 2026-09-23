"""监测回归：网站身份、失败留痕、时间口径和人工回填参数。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

import pytest  # noqa: E402

from app.application import crawler as service  # noqa: E402
from app.cli import sync_crawler as sync  # noqa: E402
from app.domain.crawler_identity import site_key  # noqa: E402
from app.repositories import crawler as repo  # noqa: E402


def test_empty_codes_do_not_merge_different_websites() -> None:
    assert site_key("", "甲网站", "海南省", "海口市") != site_key("", "乙网站", "海南省", "海口市")
    assert site_key("", "甲网站", "海南省", "海口市") == site_key("123", "甲网站", "海南省", "海口市")
    assert site_key("123", "甲网站", "", "") != site_key("123", "新名称", "", "")


async def test_source_failure_leaves_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(add=MagicMock(), commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(sync, "_days_to_sync", AsyncMock(side_effect=OSError("source offline")))
    with pytest.raises(OSError):
        await sync._run_sync(session, days=7, tasks_only=False)
    run = session.add.call_args_list[0].args[0]
    assert run.status == "failed"
    assert run.error_message == "source offline"
    assert run.finished_at is not None
    assert session.commit.await_count == 2


async def test_tasks_only_does_not_probe_data_or_move_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(add=MagicMock(), commit=AsyncMock(), rollback=AsyncMock())
    probe = AsyncMock(side_effect=AssertionError("must not query data table"))
    monkeypatch.setattr(sync, "_days_to_sync", probe)
    monkeypatch.setattr(sync, "_fetch_rules", lambda: [])
    monkeypatch.setattr(sync, "_upsert_tasks", AsyncMock(return_value=0))
    monkeypatch.setattr(sync, "recompute_health", AsyncMock(return_value=0))
    await sync._run_sync(session, days=7, tasks_only=True)
    probe.assert_not_awaited()
    run = session.add.call_args.args[0]
    assert run.status == "success"
    assert run.watermark is None


def test_explicit_days_uses_fixed_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    run = AsyncMock()
    monkeypatch.setattr(sync, "run", run)
    monkeypatch.setattr(sys, "argv", ["sync", "--days", "30"])
    sync.main()
    assert run.call_args.kwargs["days"] == 30
    assert run.call_args.kwargs["use_watermark"] is False


async def test_beijing_midnight_uses_local_yesterday(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "utcnow", lambda: datetime(2026, 9, 21, 18, tzinfo=UTC))
    for name, value in [
        ("health_distribution", {}),
        ("site_health_summary", {"sites_total": 0, "sites_all_broken": 0, "sites_partial_broken": 0}),
        ("last_sync", None),
        ("last_successful_sync", None),
        ("pending_identity_backfill", {"days": 0, "since": ""}),
        ("daily_trend", []),
    ]:
        monkeypatch.setattr(repo, name, AsyncMock(return_value=value))
    totals = AsyncMock(return_value={"rows": 0, "sites": 0, "tasks": 0})
    monkeypatch.setattr(repo, "day_totals", totals)
    await service.overview(None, trend_days=30)
    assert totals.call_args_list[0].args[1] == date(2026, 9, 21)


async def test_sparse_series_preserves_zero_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repo, "utcnow", lambda: datetime(2026, 9, 22, 6, tzinfo=UTC))
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(date(2026, 9, 20), 7)])))
    series = await repo.task_daily_series(session, site_key="code:123", tag="通知", days=7)
    assert len(series) == 7
    assert series[0] == {"date": "2026-09-22", "rows": 0}
    assert series[2] == {"date": "2026-09-20", "rows": 7}
    assert sum(point["rows"] for point in series) == 7


async def test_filter_options_match_shared_frontend_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repo, "distinct_values", AsyncMock(return_value=["验收网站"]))
    result = await service.list_options(None)
    assert result["options"]["site_name"]["items"] == ["验收网站"]
    assert result["options"]["health_status"] == {
        "items": ["正常", "观察", "断爬", "从未出数"], "truncated": False
    }


def test_source_grouping_uses_name_even_when_codes_vary(monkeypatch: pytest.MonkeyPatch) -> None:
    """用新建内存源表执行实际聚合 SQL，不仅检查生成的字符串。"""
    import sqlite3
    from contextlib import contextmanager

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    table = sync.settings.crawler_data_table
    connection.execute(
        f"CREATE TABLE {table} (author TEXT,tag TEXT,site_name TEXT,prov_name TEXT,"
        "city_name TEXT,name TEXT,content TEXT,collect_date TEXT)"
    )
    connection.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?)",
        [
            ("123", "通知", "甲网站", "海南省", "海口市", "一", "", "2026-09-22"),
            ("", "通知", "甲网站", "海南省", "海口市", "二", "", "2026-09-22"),
            ("", "通知", "乙网站", "海南省", "海口市", "三", "", "2026-09-22"),
        ],
    )

    class Cursor:
        def execute(self, sql, params):
            self.result = connection.execute(sql.replace("%s", "?"), params)

        def fetchall(self):
            return [dict(row) for row in self.result.fetchall()]

    @contextmanager
    def cursor():
        yield Cursor()

    @contextmanager
    def source():
        yield SimpleNamespace(cursor=cursor)

    monkeypatch.setattr(sync, "_mysql_connect", source)
    rows = sync._fetch_day(date(2026, 9, 22))
    assert {row["site_name"]: row["row_count"] for row in rows} == {"甲网站": 2, "乙网站": 1}
    assert {row["site_key"] for row in rows} == {site_key("", "甲网站"), site_key("", "乙网站")}
    connection.close()
