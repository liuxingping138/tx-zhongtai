"""爬虫监测状态历史补齐、较上周对比、单站曲线。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.crawler.application import crawler_stats as stats
from app.crawler.application import crawler_status as status
from app.crawler.repositories import crawler_status as repo

TODAY = date(2026, 10, 12)
YESTERDAY = date(2026, 10, 11)


class TestHistory:
    async def test_backfills_only_the_missing_span_then_records_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(repo, "missing_dates", AsyncMock(return_value=[date(2026, 9, 1), date(2026, 9, 5)]))
        backfill = AsyncMock()
        record = AsyncMock()
        monkeypatch.setattr(repo, "backfill", backfill)
        monkeypatch.setattr(repo, "record_today", record)
        await status.refresh_history(AsyncMock(), TODAY)
        assert backfill.await_args is not None
        assert backfill.await_args.args[1:] == (date(2026, 9, 1), date(2026, 9, 5))
        assert backfill.await_args.kwargs == {"normal_days": 7, "watch_days": 30}
        record.assert_awaited_once()
        assert record.await_args is not None and record.await_args.args[1] == TODAY

    async def test_complete_history_skips_the_slow_backfill(self, monkeypatch: pytest.MonkeyPatch) -> None:
        missing = AsyncMock(return_value=[])
        backfill = AsyncMock()
        monkeypatch.setattr(repo, "missing_dates", missing)
        monkeypatch.setattr(repo, "backfill", backfill)
        monkeypatch.setattr(repo, "record_today", AsyncMock())
        await status.refresh_history(AsyncMock(), TODAY)
        backfill.assert_not_awaited()
        assert missing.await_args is not None
        assert missing.await_args.args[1:] == (date(2026, 7, 14), YESTERDAY)

    async def test_week_base_needs_both_days(self, monkeypatch: pytest.MonkeyPatch) -> None:
        latest = SimpleNamespace(snapshot_date=TODAY)
        monkeypatch.setattr(repo, "latest_and_base", AsyncMock(return_value=(latest, None)))
        assert await status.week_base(AsyncMock()) is None

        base = SimpleNamespace(snapshot_date=date(2026, 10, 5), sites=5873, normal=2829, watch=924, stale=2120)
        monkeypatch.setattr(repo, "latest_and_base", AsyncMock(return_value=(latest, base)))
        assert await status.week_base(AsyncMock()) == {
            "date": "2026-10-05",
            "sites": 5873,
            "normal": 2829,
            "watch": 924,
            "stale": 2120,
        }


async def test_site_trend_fills_days_without_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "yesterday", lambda: YESTERDAY)
    series = AsyncMock(return_value=[(date(2026, 10, 10), 12, 1)])
    monkeypatch.setattr(repo, "site_series", series)
    result = await status.site_trend(AsyncMock(), site_name="市财政局", province_name="广东省", city_name="", days=30)
    assert (result["date_from"], len(result["items"])) == ("2026-09-12", 30)
    assert result["items"][-2:] == [
        {"date": "2026-10-10", "rows": 12, "sites": 1},
        {"date": "2026-10-11", "rows": 0, "sites": 0},
    ]
    assert series.await_args is not None
    assert series.await_args.kwargs["site_name"] == "市财政局"
