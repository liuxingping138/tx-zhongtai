"""同步窗口必须由入库时间水位决定，不能是固定天数。

爬虫是采集完才入库，实测入库普遍比采集日晚 1 天、近 60 天里最大滞后 4 天，
而且没有保证上限。固定 N 天窗口一旦小于实际滞后，迟到的行进库时窗口已经滑过
它的 collect_date，那天的统计就永久少算，而且不会报任何错。
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "unit-test")

import pytest

from app.crawler.application import crawler_sync as sync_crawler

TODAY = date(2026, 9, 22)


class _FakeSession:
    """只用来喂水位，不碰真实数据库。"""


async def _run(monkeypatch: pytest.MonkeyPatch, *, watermark: datetime | None, touched: set[date], **kwargs: Any):
    async def fake_last_watermark(_session: Any) -> datetime | None:
        return watermark

    def fake_affected(since_ts: datetime) -> tuple[set[date], datetime | None]:
        fake_affected.called_with = since_ts  # type: ignore[attr-defined]
        return touched, datetime(2026, 9, 22, 6, 0, tzinfo=UTC)

    monkeypatch.setattr(sync_crawler, "_last_watermark", fake_last_watermark)
    monkeypatch.setattr(sync_crawler, "_affected_days", fake_affected)
    days, mark = await sync_crawler._days_to_sync(
        _FakeSession(), today=TODAY, days=kwargs.get("days", 7), since=kwargs.get("since"), use_watermark=True
    )
    return days, mark, fake_affected


async def test_late_arrival_outside_fixed_window_is_still_recomputed(monkeypatch: pytest.MonkeyPatch) -> None:
    """滞后 20 天才入库的行，其采集日必须进重算清单——固定 7 天窗口会漏掉它。"""

    late_day = TODAY - timedelta(days=20)
    days, _mark, _ = await _run(
        monkeypatch, watermark=datetime(2026, 9, 21, 0, 0, tzinfo=UTC), touched={late_day, TODAY}
    )
    assert late_day in days, "滞后入库的采集日没有进重算清单，那天的统计会永久少算"


async def test_today_is_always_recomputed(monkeypatch: pytest.MonkeyPatch) -> None:
    """当天数据还在写，水位说没动过也必须重算。"""

    days, _mark, _ = await _run(monkeypatch, watermark=datetime(2026, 9, 22, 5, 0, tzinfo=UTC), touched=set())
    assert TODAY in days


async def test_watermark_probe_looks_back_before_the_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """查询起点要比水位再往前一点，否则长事务里稍早的时间戳会被跳过。"""

    watermark = datetime(2026, 9, 22, 5, 0, tzinfo=UTC)
    _days, _mark, fake = await _run(monkeypatch, watermark=watermark, touched={TODAY})
    assert fake.called_with < watermark  # type: ignore[attr-defined]


async def test_explicit_since_ignores_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    """人工回填要完全按指定区间来，不受水位影响。"""

    days, mark, _ = await _run(
        monkeypatch, watermark=datetime(2026, 9, 21, tzinfo=UTC), touched=set(), since=TODAY - timedelta(days=3)
    )
    assert sorted(days) == [TODAY - timedelta(days=offset) for offset in (3, 2, 1, 0)]
    assert mark is None, "人工指定区间不应推进水位"


async def test_missing_watermark_falls_back_to_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次运行没有历史水位时退回固定窗口，并且仍要建立新水位。"""

    days, mark, _ = await _run(monkeypatch, watermark=None, touched=set(), days=3)
    assert sorted(days) == [TODAY - timedelta(days=offset) for offset in (2, 1, 0)]
    assert mark is not None
