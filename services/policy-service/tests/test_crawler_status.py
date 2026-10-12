"""爬虫监测第二期：状态历史补齐、较上周对比、骤降判定、单站曲线。"""

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


def _row(name: str, recent: int, base: int, **extra: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "site_name": name,
        "province_name": "广东省",
        "city_name": "",
        "total_rows": base + recent,
        "last_created_at": None,
        "stale_days": 1,
        "status": "normal",
        "recent": recent,
        "base": base,
    }
    return SimpleNamespace(**(fields | extra))


class TestFindDrops:
    def test_site_far_below_its_own_weekly_average_is_flagged(self) -> None:
        rows = [_row("骤降站", 2, 400), _row("平稳站", 100, 400), _row("大站", 1000, 4000)]
        flagged, overall = status.find_drops(rows)
        assert [item["site_name"] for item in flagged] == ["骤降站"]
        assert (flagged[0]["recent_rows"], flagged[0]["weekly_avg"], flagged[0]["drop_rate"]) == (2, 100, 0.98)
        assert overall == pytest.approx(1102 / (4800 / 4), abs=0.001)

    def test_holiday_wide_drop_does_not_flag_every_site(self) -> None:
        """全网都只剩两成（如国庆），单个网站同样只剩两成不算骤降；明显更差的才算。"""

        rows = [_row(f"站{i}", 20, 400) for i in range(9)] + [_row("真骤降", 1, 400)]
        flagged, overall = status.find_drops(rows)
        assert overall == pytest.approx(181 / 1000, abs=0.001)
        assert [item["site_name"] for item in flagged] == ["真骤降"]

    def test_sites_with_too_little_history_are_ignored(self) -> None:
        flagged, _ = status.find_drops([_row("零星站", 0, status.DROP_MIN_BASE_ROWS - 1), _row("平稳站", 100, 400)])
        assert flagged == []

    def test_bigger_sites_come_first(self) -> None:
        rows = [_row("小站", 0, 80), _row("大站", 0, 800), _row("平稳站", 5000, 20000)]
        assert [item["site_name"] for item in status.find_drops(rows)[0]] == ["大站", "小站"]

    def test_no_data_at_all_is_not_an_error(self) -> None:
        assert status.find_drops([]) == ([], 1.0)


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


async def test_attention_uses_full_weeks_ending_yesterday(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "yesterday", lambda: YESTERDAY)
    new_stale = AsyncMock(return_value=([_row("刚停更", 0, 0, status="stale", stale_days=33)], 1))
    windows = AsyncMock(return_value=[])
    monkeypatch.setattr(repo, "new_stale", new_stale)
    monkeypatch.setattr(repo, "window_rows", windows)
    result = await status.attention(AsyncMock())
    assert new_stale.await_args is not None
    assert new_stale.await_args.kwargs == {"watch_days": 30, "within_days": 7, "limit": status.ATTENTION_LIMIT}
    assert windows.await_args is not None
    assert windows.await_args.kwargs == {
        "base_start": date(2026, 9, 7),
        "recent_start": date(2026, 10, 5),
        "end": YESTERDAY,
    }
    assert result["new_stale"]["items"][0]["stale_days"] == 33
    assert result["rules"] == {
        "new_stale_from": 31,
        "new_stale_to": 37,
        "drop_percent": 80,
        "drop_base_weeks": 4,
        "date_to": "2026-10-11",
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
