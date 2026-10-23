"""爬虫配置同步：规则表里有的网站编码，未爬、没填状态的信源改成已爬并记当天上线，已爬、异常的不动。

在 P6 的 scheduler_test 库跑，规则表用替身。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.database import SessionLocal, engine
from app.crawlconfig.application import rules_sync
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
