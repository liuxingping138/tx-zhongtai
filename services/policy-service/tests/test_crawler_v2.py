"""爬虫监测 v2：按天合并、同步范围规划、中断识别与 CLI 参数。"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

import pytest

from app.application import crawler_v2 as service
from app.cli import sync_crawler_v2 as sync
from app.repositories import crawler_v2 as repo

TODAY = date(2026, 9, 23)


def _source_row(name: str, count: int, created: datetime | None, published: str | None) -> dict[str, object]:
    return {
        "site_name": name,
        "province_name": "广东省",
        "city_name": "惠州市",
        "row_count": count,
        "last_created": created,
        "last_published": published,
    }


def test_source_time_is_beijing_and_stored_as_utc() -> None:
    rows = sync.merge_day_rows(TODAY, [_source_row("市财政局", 3, datetime(2026, 9, 23, 8, 0), "2026-09-22")])
    assert rows[0]["last_created_at"] == datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
    assert rows[0]["last_published_date"] == date(2026, 9, 22)


def test_rows_colliding_on_local_key_are_merged_not_rejected() -> None:
    """MySQL 排序规则会把本地视为相同的键分成两组（或反之），写入前必须合并，否则整天 upsert 失败。"""

    rows = sync.merge_day_rows(
        TODAY,
        [
            _source_row("市财政局", 3, datetime(2026, 9, 23, 8, 0), "2026-09-20"),
            _source_row("市财政局", 2, datetime(2026, 9, 23, 9, 0), None),
        ],
    )
    assert len(rows) == 1
    assert rows[0]["row_count"] == 5
    assert rows[0]["last_created_at"] == datetime(2026, 9, 23, 1, 0, tzinfo=UTC)
    assert rows[0]["last_published_date"] == date(2026, 9, 20)


def test_invalid_publish_date_is_ignored() -> None:
    rows = sync.merge_day_rows(TODAY, [_source_row("市财政局", 1, None, "2026-09-99")])
    assert rows[0]["last_published_date"] is None
    assert rows[0]["last_created_at"] is None


def test_different_cities_with_same_site_name_stay_separate() -> None:
    first = _source_row("市财政局", 1, None, None)
    second = dict(first, city_name="中山市")
    assert len(sync.merge_day_rows(TODAY, [first, second])) == 2


@pytest.mark.asyncio
async def test_incremental_without_watermark_requires_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "_last_watermark", AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="回填"):
        await sync.plan(MagicMock(), mode=sync.MODE_INCREMENTAL, today=TODAY, days=7, since=None, skip_existing=False)


@pytest.mark.asyncio
async def test_incremental_recomputes_touched_days_and_today(monkeypatch: pytest.MonkeyPatch) -> None:
    mark = datetime(2026, 9, 22, 12, tzinfo=UTC)
    newer = mark + timedelta(hours=10)
    fetch = MagicMock(return_value=({date(2026, 9, 1), date(2026, 9, 21)}, newer))
    monkeypatch.setattr(sync, "_last_watermark", AsyncMock(return_value=mark))
    monkeypatch.setattr(sync, "fetch_affected_days", fetch)
    targets, new_mark = await sync.plan(
        MagicMock(), mode=sync.MODE_INCREMENTAL, today=TODAY, days=7, since=None, skip_existing=False
    )
    assert targets == [TODAY, date(2026, 9, 21), date(2026, 9, 1)]
    assert new_mark == newer
    fetch.assert_called_once_with(mark - timedelta(hours=2))


@pytest.mark.asyncio
async def test_incremental_keeps_watermark_when_nothing_new(monkeypatch: pytest.MonkeyPatch) -> None:
    mark = datetime(2026, 9, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(sync, "_last_watermark", AsyncMock(return_value=mark))
    monkeypatch.setattr(sync, "fetch_affected_days", MagicMock(return_value=(set(), None)))
    targets, new_mark = await sync.plan(
        MagicMock(), mode=sync.MODE_INCREMENTAL, today=TODAY, days=7, since=None, skip_existing=False
    )
    assert targets == [TODAY]
    assert new_mark == mark


@pytest.mark.asyncio
async def test_repair_uses_fixed_window_and_never_moves_watermark() -> None:
    targets, mark = await sync.plan(
        MagicMock(), mode=sync.MODE_REPAIR, today=TODAY, days=3, since=None, skip_existing=False
    )
    assert targets == [TODAY, date(2026, 9, 22), date(2026, 9, 21)]
    assert mark is None


@pytest.mark.asyncio
async def test_backfill_starts_from_source_first_day(monkeypatch: pytest.MonkeyPatch) -> None:
    source_mark = datetime(2026, 9, 23, 0, tzinfo=UTC)
    monkeypatch.setattr(sync, "fetch_source_bounds", MagicMock(return_value=(date(2026, 9, 20), source_mark)))
    targets, mark = await sync.plan(
        MagicMock(), mode=sync.MODE_BACKFILL, today=TODAY, days=7, since=None, skip_existing=False
    )
    assert targets == [TODAY, date(2026, 9, 22), date(2026, 9, 21), date(2026, 9, 20)]
    assert mark == source_mark


@pytest.mark.asyncio
async def test_resumed_backfill_keeps_earlier_watermark_and_skips_done_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """续跑沿用中断批次的水位：中断期间入库到已完成日期的数据，下次日常增量才能补上。"""

    earlier = datetime(2026, 9, 22, 0, tzinfo=UTC)
    monkeypatch.setattr(
        sync, "fetch_source_bounds", MagicMock(return_value=(date(2026, 9, 19), earlier + timedelta(days=1)))
    )
    monkeypatch.setattr(sync, "_unfinished_backfill_mark", AsyncMock(return_value=earlier))
    monkeypatch.setattr(
        sync,
        "_existing_days",
        AsyncMock(return_value={TODAY, date(2026, 9, 22), date(2026, 9, 21), date(2026, 9, 20)}),
    )
    targets, mark = await sync.plan(
        MagicMock(), mode=sync.MODE_BACKFILL, today=TODAY, days=7, since=None, skip_existing=True
    )
    # 当天和昨天总是重算；已完成的更早日期跳过。
    assert targets == [TODAY, date(2026, 9, 22), date(2026, 9, 19)]
    assert mark == earlier


class _RunHistory:
    """按 started_at 倒序返回回填批次，记录收到的 SQL。"""

    def __init__(self, rows: list[tuple[str, datetime | None]]) -> None:
        self.rows = rows
        self.sql = ""

    async def execute(self, stmt: object) -> SimpleNamespace:
        self.sql = str(stmt)
        return SimpleNamespace(all=lambda: self.rows)


@pytest.mark.asyncio
async def test_resume_mark_excludes_the_current_run() -> None:
    """本次批次已以 running、水位为空写入；不排除它，续跑就永远拿不到上次中断的水位。"""

    earlier = datetime(2026, 9, 22, tzinfo=UTC)
    session = _RunHistory([("failed", earlier)])
    mark = await sync._unfinished_backfill_mark(session, exclude_run_id=uuid.uuid4())  # type: ignore[arg-type]
    assert mark == earlier
    assert "policy_crawler_v2_sync_runs.id !=" in session.sql


@pytest.mark.asyncio
async def test_resume_mark_stops_at_last_successful_backfill() -> None:
    """成功回填之前的失败批次已被覆盖，沿用它的旧水位只会让下次增量重算大量日期。"""

    old = datetime(2026, 1, 1, tzinfo=UTC)
    session = _RunHistory([("success", datetime(2026, 2, 1, tzinfo=UTC)), ("failed", old)])
    assert await sync._unfinished_backfill_mark(session, exclude_run_id=None) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resume_mark_skips_batches_that_died_before_recording_a_mark() -> None:
    earlier = datetime(2026, 9, 22, tzinfo=UTC)
    session = _RunHistory([("running", None), ("failed", earlier)])
    assert await sync._unfinished_backfill_mark(session, exclude_run_id=None) == earlier  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_running_batch_without_lock_is_reported_as_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    run = SimpleNamespace(status="running", started_at=datetime(2026, 9, 23, tzinfo=UTC), error_message=None)
    monkeypatch.setattr(repo, "last_run", AsyncMock(return_value=run))
    monkeypatch.setattr(repo, "last_successful_run", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "sync_lock_held", AsyncMock(return_value=False))
    status = await service._sync_status(MagicMock())
    assert status["status"] == "interrupted"


@pytest.mark.asyncio
async def test_running_batch_holding_lock_stays_running(monkeypatch: pytest.MonkeyPatch) -> None:
    run = SimpleNamespace(status="running", started_at=datetime(2026, 9, 23, tzinfo=UTC), error_message=None)
    monkeypatch.setattr(repo, "last_run", AsyncMock(return_value=run))
    monkeypatch.setattr(repo, "last_successful_run", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "sync_lock_held", AsyncMock(return_value=True))
    assert (await service._sync_status(MagicMock()))["status"] == "running"


@pytest.mark.parametrize(
    "argv",
    [
        ["--since", "2024-01-01"],
        ["--skip-existing"],
        ["--backfill", "--days", "3"],
        ["--days", "0"],
    ],
)
def test_cli_rejects_ambiguous_arguments(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["sync_crawler_v2", *argv])
    monkeypatch.setattr(sync, "run", MagicMock())
    with pytest.raises(SystemExit):
        sync.main()


def test_status_filter_is_exact_and_unknown_field_rejected() -> None:
    assert len(repo._conditions({"status": "stale", "province_name": "广东"})) == 2
    with pytest.raises(KeyError):
        repo._conditions({"tag": "x"})
