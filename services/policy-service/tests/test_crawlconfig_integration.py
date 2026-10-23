"""爬虫配置同步：规则表里有的网站编码，未爬、没填状态的信源改成已爬并记当天上线，已爬、异常的不动。

在 P6 的 scheduler_test 库跑，规则表用替身。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import get_settings
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


async def test_sync_marks_only_pending_sources_and_records_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionLocal() as session:
        session.add_all(
            [
                _source("A1", "未爬"),
                _source("A2", ""),
                _source("A3", "已爬", "2026-10-22"),
                _source("A4", "异常", "2026-09-01"),
                _source("A5", "未爬"),  # 规则表里没有
            ]
        )
        await session.commit()
    rules = RuleCodes(rows=6, codes={"A1", "A2", "A3", "A4", "Z9"}, blank_rows=1)
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda: rules)
    sync_id = uuid.uuid4()
    await rules_sync.run(sync_id)

    async with SessionLocal() as session:
        rows = {row.site_code: row for row in (await session.scalars(select(Source))).all()}
        today = rows["A1"].online_date
        assert len(today) == 10
        assert {code: (row.crawler_status, row.online_date) for code, row in rows.items()} == {
            "A1": ("已爬", today),
            "A2": ("已爬", today),
            "A3": ("已爬", "2026-10-22"),
            "A4": ("异常", "2026-09-01"),
            "A5": ("未爬", ""),
        }
        assert rows["A1"].version == 2 and rows["A1"].updated_by_name == "爬虫配置同步"
        assert await rules_sync.summary(session, sync_id) == {
            "status": "success",
            "rule_rows": 6,
            "rule_codes": 5,
            "blank_code_rows": 1,
            "matched": 4,
            "marked": 2,
            "unknown_codes": 1,
        }

    # 再跑一次：都已经是已爬，什么也不改。
    again = uuid.uuid4()
    await rules_sync.run(again)
    async with SessionLocal() as session:
        latest = await rules_sync.latest(session)
        assert latest is not None and latest["marked"] == 0


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


async def test_report_counts_new_sites_per_week_and_keeps_earlier_ones_as_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """统计起始周之前上线的、已爬没填日期的都算期初存量；所选周的新增按上线时间落在周一到周日。"""

    monkeypatch.setattr(get_settings(), "crawler_config_report_start", date(2026, 10, 26))
    async with SessionLocal() as session:
        session.add_all(
            [
                _source("B1", "已爬", "2026-10-22"),  # 起始周之前：期初
                _source("B2", "已爬", ""),  # 已爬没填日期：期初
                _source("B3", "已爬", "2026-10-27", province="河北省"),  # 第一周
                _source("B4", "异常", "2026-11-03"),  # 第二周，后来标了异常
                _source("B5", "已爬", "2026-11-08"),  # 第二周周日
                _source("B6", "未爬"),
                _source("B7", "", province=""),
            ]
        )
        await session.commit()
    async with SessionLocal() as session:
        data = await report.build_report(session, date(2026, 11, 5))
    assert (data["week_from"], data["week_to"], data["counted"]) == ("2026-11-02", "2026-11-08", True)
    assert data["baseline"] == 2
    assert data["previous_new"] == 1
    assert [(item["new"], item["cumulative"]) for item in data["trend"]] == [(1, 3), (2, 5)]
    assert [site["site_code"] for site in data["new_sites"]] == ["B4", "B5"]
    assert {
        row["province_name"]: (row["total"], row["online"], row["pending"], row["abnormal"], row["new"])
        for row in data["provinces"]
    } == {
        "北京市": (5, 3, 1, 1, 2),
        "河北省": (1, 1, 0, 0, 0),
        "（未填省份）": (1, 0, 1, 0, 0),
    }
    assert data["totals"]["total"] == 7 and data["totals"]["coverage"] == 57.1
    # 分省每周：和趋势同样两周（10-26 那周、11-02 那周）。
    assert {row["province_name"]: row["weekly"] for row in data["provinces"]} == {
        "北京市": [0, 2],
        "河北省": [1, 0],
        "（未填省份）": [0, 0],
    }

    # 起点不是周一时，起点所在那周只从起点算起。
    monkeypatch.setattr(get_settings(), "crawler_config_report_start", date(2026, 11, 4))
    async with SessionLocal() as session:
        partial = await report.build_report(session, date(2026, 11, 5))
    assert (partial["counted"], [site["site_code"] for site in partial["new_sites"]]) == (True, ["B5"])
    assert partial["baseline"] == 4  # B1、B2、B3、B4（11-03，起点前一天）
    monkeypatch.setattr(get_settings(), "crawler_config_report_start", date(2026, 10, 26))

    # 起始周之前的周：不算新增，趋势为空。
    async with SessionLocal() as session:
        before = await report.build_report(session, date(2026, 10, 23))
    assert (before["counted"], before["totals"]["new"], before["trend"], before["new_sites"]) == (False, 0, [], [])
