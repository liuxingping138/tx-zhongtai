"""在全新隔离库验收爬虫同步；仅允许 test 环境且目标表必须为空。

镜像内运行：.venv/bin/python /tmp/crawler_database_acceptance.py
不连接外部 MySQL；构造源端快照，验证真实 PostgreSQL 写入、重算、查询与失败留痕。
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))

from platform_common.clock import BEIJING
from sqlalchemy import text

from app.application import crawler as service
from app.cli import sync_crawler as sync
from app.core.database import SessionLocal, engine
from app.domain.crawler_identity import site_key
from app.repositories import crawler as repo


def rule(name: str, tag: str, code: str = "") -> dict:
    return dict(
        correlation=name + tag,
        site_key=site_key(code, name),
        site_code=code,
        site_name=name,
        province_name="海南省",
        city_name="海口市",
        tag=tag,
        source_url="https://example.com/policies",
        rule_state=1,
    )


def daily(day, name, tag, rows, code="") -> dict:
    return dict(
        collect_date=day,
        site_key=site_key(code, name),
        site_code=code,
        site_name=name,
        province_name="海南省",
        city_name="海口市",
        tag=tag,
        row_count=rows,
        named_count=rows,
        content_count=0,
        identity_verified=True,
    )


async def main() -> None:
    assert str(sync.settings.environment) == "test", "仅允许 test 环境"
    async with SessionLocal() as s:
        assert await s.scalar(text("SELECT count(*) FROM policy_crawler_sync_runs")) == 0, "必须使用全新空库"
        assert await repo.count_filtered(s, {}) == 0
        empty = await service.overview(s, trend_days=30)
        assert empty["cards"]["total_tasks"] == 0 and empty["last_sync"] is None
    results = ["empty database / migrations"]
    today = datetime.now(BEIJING).date()
    rules = [rule("验收甲网站", "通知", "A"), rule("验收乙网站", "通知"), rule("验收丙网站", "政策")]
    rows = [daily(today, "验收甲网站", "通知", 3), daily(today, "验收乙网站", "通知", 5)]
    with patch.object(sync, "_fetch_rules", return_value=rules), patch.object(sync, "_fetch_day", return_value=rows):
        await sync.run(days=1, tasks_only=False, use_watermark=False)
    async with SessionLocal() as s:
        data = await service.overview(s, trend_days=30)
        assert data["cards"]["total_tasks"] == 3
        assert data["cards"]["sites_total"] == 3
        assert (await repo.get_task(s, site_key=site_key("", "验收甲网站"), tag="通知")).count_total == 3
        assert (await repo.get_task(s, site_key=site_key("", "验收乙网站"), tag="通知")).count_total == 5
        assert await repo.count_filtered(s, {"health_status": "never"}) == 1
        series = await repo.task_daily_series(s, site_key=site_key("", "验收甲网站"), tag="通知", days=90)
        assert len(series) == 90 and sum(p["rows"] for p in series) == 3
        # 旧编码聚合尚未按名称回填时，断点续跑不能将它误判为已完成。
        await s.execute(text("UPDATE policy_crawler_daily_stats SET identity_verified = false"))
        assert today not in await sync._existing_days(s, today, today)
        await s.rollback()
    results += ["name identity / empty codes / rule-data matching", "health and complete 90-day series"]
    # 配置删除后不再显示“在配”；历史采集仍保留。
    with patch.object(sync, "_fetch_rules", return_value=[rules[0]]):
        await sync.run(days=1, tasks_only=True)
    async with SessionLocal() as s:
        assert not (await repo.get_task(s, site_key=site_key("", "验收乙网站"), tag="通知")).in_rules
        assert await repo.get_task(s, site_key=site_key("", "验收丙网站"), tag="政策") is None
    # 重算源端空日期，旧分组必须消失。
    with patch.object(sync, "_fetch_rules", return_value=[rules[0]]), patch.object(sync, "_fetch_day", return_value=[]):
        await sync.run(days=1, tasks_only=False, use_watermark=False)
    async with SessionLocal() as s:
        assert (await repo.day_totals(s, today))["rows"] == 0
        assert await repo.get_task(s, site_key=site_key("", "验收乙网站"), tag="通知") is None
    results += ["removed rules and stale health cleanup", "empty-day snapshot replacement"]
    # 水位查询阶段失败也必须有同步记录。
    with patch.object(sync, "_affected_days", side_effect=OSError("acceptance: source unavailable")):
        try:
            await sync.run(days=1, tasks_only=False)
        except OSError:
            pass
        else:
            raise AssertionError("expected source failure")
    async with SessionLocal() as s:
        assert (await repo.last_sync(s)).status == "failed"
        assert (await repo.last_successful_sync(s)).status == "success"
    results.append("source probe failure persisted / last success retained")
    # 会话级锁不会被每日 commit 释放。
    async with engine.connect() as c:
        await c.execute(text("SELECT pg_advisory_lock(72120260922)"))
        await c.commit()
        try:
            try:
                await sync.run(days=1, tasks_only=True)
            except RuntimeError as exc:
                assert "已有爬虫同步" in str(exc)
            else:
                raise AssertionError("concurrent sync was allowed")
        finally:
            await c.execute(text("SELECT pg_advisory_unlock(72120260922)"))
            await c.commit()
    results.append("concurrent sync exclusion")
    # 独立的验收数据，不复制旧业务库；覆盖分页、空编码、多状态和长标签。
    names = ["验收·省发展和改革委员会", "验收·市财政局", "验收·市商务局", "验收·市科技局"]
    tags = [
        "政策文件",
        "通知公告",
        "政策解读",
        "政府信息公开",
        "惠企政策",
        "专项资金申报",
        "公开目录 > 财政预决算与重大项目建设信息",
    ]
    rules = [rule(name, tag, "" if i % 2 else f"QA{i:03}") for i, name in enumerate(names) for tag in tags]

    def fixture_day(day):
        age = (today - day).days
        data = []
        for n, name in enumerate(names):
            for t, tag in enumerate(tags):
                state = (n + t) % 4
                last_age = (1, 12, 40, 999)[state]
                if age >= last_age and age % 7 not in (0, 6):
                    data.append(daily(day, name, tag, (n + 1) * 3 + (t + 1) * 2 + age % 5))
        return data

    with (
        patch.object(sync, "_fetch_rules", return_value=rules),
        patch.object(sync, "_fetch_day", side_effect=fixture_day),
    ):
        await sync.run(days=90, tasks_only=False, use_watermark=False)
    async with SessionLocal() as s:
        assert await repo.count_filtered(s, {}) == 28
        distribution = await repo.health_distribution(s)
        assert set(distribution) == {"normal", "watch", "broken", "never"}
        for status in distribution:
            page, total = await repo.list_items(s, filters={"health_status": status}, page=1, page_size=100)
            exported = await repo.list_filtered(s, {"health_status": status})
            assert len(page) == total == len(exported)
        assert len(await repo.daily_trend(s, 90)) == 90
    results.append("seeded independent QA fixture / four statuses / export parity")
    print(json.dumps({"passed": results, "fixture_tasks": 28, "database": engine.url.database}, ensure_ascii=False))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
