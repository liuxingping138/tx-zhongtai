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
from app.crawlconfig.domain.expand import ColumnRule
from app.crawlconfig.domain.models import ConfigSyncRun
from app.crawlconfig.repositories import rules_source
from app.crawlconfig.repositories.rules_source import RuleCodes
from app.policy.domain.models import Source

pytestmark = pytest.mark.skipif(os.environ.get("SCHEDULER_INTEGRATION") != "1", reason="需要独立 scheduler_test 数据库")
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _source(code: str, status: str, online_date: str = "", province: str = "北京市", rule_date: str = "") -> Source:
    return Source(
        internal_id=uuid.uuid4().hex,
        site_code=code,
        site_name=f"网站{code}",
        province_name=province,
        crawler_status=status,
        online_date=online_date,
        rule_date=rule_date,
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
                # 同步见过它 10-01 的规则，后来最早的规则被删，剩下的更晚：不往后挪
                _source("A7", "已爬", "2026-10-01", rule_date="2026-10-01"),
                # 导入时直接标了已爬、上线时间随手填的，规则是后来才建的：第一次见到规则时对齐，算进建规则那一周
                _source("A8", "已爬", "2024-10-01"),
            ]
        )
        await session.commit()
    first = {"A1": date(2026, 10, 23), "A2": date(2024, 10, 15), "A3": date(2026, 10, 23), "A4": date(2026, 10, 10)}
    later = {"A6": date(2026, 10, 16), "A7": date(2026, 10, 20), "A8": date(2026, 10, 30), "Z9": date(2026, 10, 23)}
    rules = RuleCodes(rows=9, first_dates={**first, **later}, blank_rows=1)
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda *_: rules)
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
            "A7": ("已爬", "2026-10-01"),
            "A8": ("已爬", "2026-10-30"),
        }
        assert rows["A1"].version == 2 and rows["A1"].updated_by_name == "爬虫配置同步"
        assert rows["A6"].version == 1
        # 见过的规则日期都记下了，A7 记的是更早那次见到的。
        assert {code: row.rule_date for code, row in rows.items() if code in ("A1", "A6", "A7")} == {
            "A1": "2026-10-23",
            "A6": "2026-10-16",
            "A7": "2026-10-01",
        }
        assert await rules_sync.summary(session, sync_id) == {
            "status": "success",
            "rule_rows": 9,
            "rule_codes": 8,
            "blank_code_rows": 1,
            "matched": 7,
            "marked": 2,
            "redated": 2,
            "unknown_codes": 1,
            "added": 0,
            "moved": 0,
            "conflicts": 0,
            "duplicates": 0,
        }

    # 再跑一次：日期已经对齐，什么也不改。
    await rules_sync.run(uuid.uuid4())
    async with SessionLocal() as session:
        latest = await rules_sync.latest(session)
        assert latest is not None and (latest["marked"], latest["redated"]) == (0, 0)


async def test_rules_from_the_expand_day_become_one_source_row_each(monkeypatch: pytest.MonkeyPatch) -> None:
    """从展开那天起建的规则，每条在信源表里一行：标签、链接换成规则的，其余照抄网站那行，网站编码共用。"""

    async with SessionLocal() as session:
        site = _source("B1", "已爬", "2024-10-01")
        site.department, site.url, site.tag = "市政府办公室", "https://b1.gov.cn", "政策|通知公告"
        session.add_all([site, _source("B2", "已爬", "2026-10-10", rule_date="2026-10-10")])
        await session.commit()
    columns = [
        ColumnRule("r1", "B1", "政策文件", "https://b1.gov.cn/zcwj", date(2026, 10, 30)),
        ColumnRule("r2", "B1", "通知公告", "https://b1.gov.cn/tzgg", date(2026, 10, 30)),
        ColumnRule("r3", "B2", "新栏目", "https://b2.gov.cn/new", date(2026, 10, 30)),
        ColumnRule("r4", "Z9", "没有这个网站", "https://z9.gov.cn", date(2026, 10, 30)),
    ]
    rules = RuleCodes(rows=5, first_dates={"B2": date(2026, 10, 10)}, columns=columns)
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda *_: rules)
    sync_id = uuid.uuid4()
    await rules_sync.run(sync_id)

    async with SessionLocal() as session:
        rows = (await session.scalars(select(Source).order_by(Source.site_code, Source.rule_id))).all()
        assert [(row.site_code, row.rule_id, row.tag, row.url, row.online_date) for row in rows] == [
            # B1 之前没有规则：原来那行改成第一个栏目，第二个栏目新增一行
            ("B1", "r1", "政策文件", "https://b1.gov.cn/zcwj", "2026-10-30"),
            ("B1", "r2", "通知公告", "https://b1.gov.cn/tzgg", "2026-10-30"),
            # B2 之前配过规则：原来那行留着、日期不变，新栏目另起一行
            ("B2", "", "", "", "2026-10-10"),
            ("B2", "r3", "新栏目", "https://b2.gov.cn/new", "2026-10-30"),
        ]
        added = next(row for row in rows if row.rule_id == "r2")
        assert (added.department, added.site_name, added.crawler_status, added.created_by_name) == (
            "市政府办公室",
            "网站B1",
            "已爬",
            "爬虫配置同步",
        )
        summary = await rules_sync.summary(session, sync_id)
        assert summary is not None
        assert (summary["added"], summary["matched"], summary["unknown_codes"]) == (2, 2, 1)

    # 再跑一次：规则 ID 都记在行上了，不会再展开。
    again = uuid.uuid4()
    await rules_sync.run(again)
    async with SessionLocal() as session:
        assert len((await session.scalars(select(Source))).all()) == 4
        latest = await rules_sync.summary(session, again)
        assert latest is not None and (latest["added"], latest["marked"], latest["redated"]) == (0, 0, 0)


async def test_a_rule_moved_to_another_site_code_keeps_its_row_and_the_sync_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规则展开以后爬虫同事改了它的网站编码：原来按现在的编码取不到已展开的那行，又展开一次，
    撞规则 ID 唯一索引整次回滚、天天失败。现在那行留在原编码下照常跟着规则走，批次记下改了编码的条数。"""

    async with SessionLocal() as session:
        session.add_all([_source("C1", "已爬", "2024-10-01"), _source("C2", "未爬")])
        await session.commit()
    first = [ColumnRule("m1", "C1", "政策文件", "https://c1.gov.cn/zcwj", date(2026, 10, 30))]
    rules = RuleCodes(rows=1, first_dates={}, columns=first)
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda *_: rules)
    await rules_sync.run(uuid.uuid4())

    moved = RuleCodes(
        rows=1,
        first_dates={},
        columns=[ColumnRule("m1", "C2", "政策文件", "https://c1.gov.cn/zcwj", date(2026, 10, 30))],
    )
    monkeypatch.setattr(rules_source, "read_rule_codes", lambda *_: moved)
    sync_id = uuid.uuid4()
    await rules_sync.run(sync_id)
    async with SessionLocal() as session:
        rows = (await session.scalars(select(Source).order_by(Source.site_code))).all()
        assert [(row.site_code, row.rule_id, row.crawler_status) for row in rows] == [
            ("C1", "m1", "已爬"),
            ("C2", "", "未爬"),
        ]
        summary = await rules_sync.summary(session, sync_id)
        assert summary is not None and (summary["status"], summary["moved"], summary["added"]) == ("success", 1, 0)


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
