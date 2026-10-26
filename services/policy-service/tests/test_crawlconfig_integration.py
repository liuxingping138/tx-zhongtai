"""爬虫配置同步和统计：规则表里有的网站标成已爬、上线时间对齐成规则创建日期，异常不动；
统计按上线时间分周，统一补填日的算期初。在 P6 的 scheduler_test 库跑，规则表用替身。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.database import SessionLocal, engine
from app.crawlconfig.application import report, rules_sync
from app.crawlconfig.domain.models import ConfigSyncRun
from app.crawlconfig.repositories import rules_source
from app.crawlconfig.repositories.rules_source import RuleCodes
from app.policy.domain.models import Source

pytestmark = pytest.mark.skipif(os.environ.get("SCHEDULER_INTEGRATION") != "1", reason="需要独立 scheduler_test 数据库")
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _source(code: str, status: str, online_date: str = "", province: str = "北京市") -> Source:
    return Source(
        internal_id=uuid.uuid4().hex,
        site_code=code,
        site_name=f"网站{code}",
        province_name=province,
        crawler_status=status,
        online_date=online_date,
        created_at=NOW,
        created_by_id="u1",
        created_by_name="测试",
        updated_at=NOW,
        updated_by_id="u1",
        updated_by_name="测试",
    )


@pytest_asyncio.fixture(autouse=True)
async def clean() -> Any:
    async with SessionLocal() as session:
        await session.execute(delete(Source))
        await session.execute(delete(ConfigSyncRun))
        await session.commit()
    yield
    await engine.dispose()


async def test_sync_dates_sites_by_rule_creation_and_leaves_abnormal_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionLocal() as session:
        session.add_all(
            [
                _source("A1", "未爬"),
                _source("A2", ""),
                _source("A3", "已爬", "2026-10-22"),  # 统一补填的日期：对齐成规则创建日期
                _source("A4", "异常", "2026-09-01"),
                _source("A5", "未爬"),  # 规则表里没有
                _source("A6", "已爬", "2026-10-16"),  # 已经对齐，不算修改
            ]
        )
        await session.commit()
    first = {"A1": date(2026, 10, 23), "A2": date(2024, 10, 15), "A3": date(2026, 10, 23), "A4": date(2026, 10, 10)}
    rules = RuleCodes(rows=8, first_dates={**first, "A6": date(2026, 10, 16), "Z9": date(2026, 10, 23)}, blank_rows=1)
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda: rules)
    sync_id = uuid.uuid4()
    await rules_sync.run(sync_id)

    async with SessionLocal() as session:
        rows = {row.site_code: row for row in (await session.scalars(select(Source))).all()}
        assert {code: (row.crawler_status, row.online_date) for code, row in rows.items()} == {
            "A1": ("已爬", "2026-10-23"),
            "A2": ("已爬", "2024-10-15"),
            "A3": ("已爬", "2026-10-23"),
            "A4": ("异常", "2026-09-01"),
            "A5": ("未爬", ""),
            "A6": ("已爬", "2026-10-16"),
        }
        assert rows["A1"].version == 2 and rows["A1"].updated_by_name == "爬虫配置同步"
        assert rows["A6"].version == 1
        assert await rules_sync.summary(session, sync_id) == {
            "status": "success",
            "rule_rows": 8,
            "rule_codes": 6,
            "blank_code_rows": 1,
            "matched": 5,
            "marked": 2,
            "redated": 1,
            "unknown_codes": 1,
        }

    # 再跑一次：日期已经对齐，什么也不改。
    await rules_sync.run(uuid.uuid4())
    async with SessionLocal() as session:
        latest = await rules_sync.latest(session)
        assert latest is not None and (latest["marked"], latest["redated"]) == (0, 0)


async def test_abandon_marks_a_running_batch_failed() -> None:
    sync_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(ConfigSyncRun(id=sync_id, status="running", started_at=NOW))
        await session.commit()
    async with SessionLocal() as session:
        await rules_sync.abandon(session, sync_id, "执行超时")
        await session.commit()
        row = await session.get(ConfigSyncRun, sync_id)
        assert row is not None and (row.status, row.error_message) == ("failed", "执行超时")


async def test_report_counts_sites_per_period_and_keeps_backfilled_ones_as_baseline() -> None:
    """统一补填日上线的、已爬没填日期的算期初；所选这期的数量按上线时间落在周一到周日，按月也一样口径。"""

    async with SessionLocal() as session:
        session.add_all(
            [
                _source("B1", "已爬", "2026-10-22"),  # 统一补填日：期初
                _source("B2", "已爬", ""),  # 已爬没填日期：期初
                _source("B3", "已爬", "2026-10-16", province="河北省"),  # 上一周
                _source("B4", "异常", "2026-10-23"),  # 本周，后来标了异常
                _source("B5", "已爬", "2026-10-25"),  # 本周周日
                _source("B6", "已爬", "2024-10-15"),  # 很早以前
                _source("B7", "未爬"),
                _source("B8", "", province=""),
            ]
        )
        await session.commit()
    async with SessionLocal() as session:
        data = await report.build_report(session, "week", date(2026, 10, 23))
        month = await report.build_report(session, "month", date(2026, 10, 1))
    assert (data["period_from"], data["period_to"], data["backfill_date"]) == ("2026-10-19", "2026-10-25", "2026-10-22")
    assert (data["baseline"], data["new"], data["previous_new"]) == (2, 2, 1)
    assert data["provinces"] == [{"province_name": "北京市", "new": 2}]
    assert [site["site_code"] for site in data["new_sites"]] == ["B4", "B5"]
    counts = {
        row["province_name"]: (row["total"], row["online"], row["pending"], row["abnormal"]) for row in data["status"]
    }
    assert counts == {"北京市": (6, 4, 1, 1), "河北省": (1, 1, 0, 0), "（未填省份）": (1, 0, 1, 0)}
    assert (month["new"], month["provinces"]) == (
        3,
        [{"province_name": "北京市", "new": 2}, {"province_name": "河北省", "new": 1}],
    )
