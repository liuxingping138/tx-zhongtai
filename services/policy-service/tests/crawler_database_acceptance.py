"""在全新隔离库验收爬虫同步；仅允许 test 环境且目标表必须为空。

镜像内运行：.venv/bin/python /tmp/crawler_database_acceptance.py
不连接外部 MySQL；构造源端快照，验证真实 PostgreSQL 写入、重算、查询与失败留痕。
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))

from platform_common.clock import BEIJING
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.crawler.application import crawler as service
from app.crawler.application import crawler_sync as sync
from app.crawler.domain.identity import site_key
from app.crawler.repositories import crawler as repo
from app.crawler.repositories.crawler import SYNC_LOCK_KEY


def rule(name: str, tag: str, code: str = "") -> dict:
    return {
        "correlation": name + tag,
        "site_key": site_key(code, name),
        "site_code": code,
        "site_name": name,
        "province_name": "海南省",
        "city_name": "海口市",
        "tag": tag,
        "source_url": "https://example.com/policies",
        "rule_state": 1,
    }


def daily(day, name, tag, rows, code="") -> dict:
    return {
        "collect_date": day,
        "site_key": site_key(code, name),
        "site_code": code,
        "site_name": name,
        "province_name": "海南省",
        "city_name": "海口市",
        "tag": tag,
        "row_count": rows,
        "named_count": rows,
        "content_count": 0,
        "identity_verified": True,
    }


def patch_source(**targets: object) -> ExitStack:
    """替换源端读取：键是 crawler_sync 里的函数名，值是 return_value 或带 side_effect 的 patch 参数。"""

    stack = ExitStack()
    for name, value in targets.items():
        kwargs = value if isinstance(value, dict) else {"return_value": value}
        stack.enter_context(patch.object(sync, name, **kwargs))
    return stack


async def check_empty_database() -> str:
    assert str(sync.settings.environment) == "test", "仅允许 test 环境"
    async with SessionLocal() as s:
        assert await s.scalar(text("SELECT count(*) FROM policy_crawler_sync_runs")) == 0, "必须使用全新空库"
        assert await repo.count_filtered(s, {}) == 0
        empty = await service.overview(s, trend_days=30)
        assert empty["cards"]["total_tasks"] == 0 and empty["last_sync"] is None
    return "empty database / migrations"


async def check_first_sync(today: date, rules: list[dict]) -> str:
    rows = [daily(today, "验收甲网站", "通知", 3), daily(today, "验收乙网站", "通知", 5)]
    with patch_source(fetch_rules=rules, fetch_day=rows):
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
    return "name identity / empty codes / rule-data matching / health and complete 90-day series"


async def check_removed_rules(today: date, kept_rule: dict) -> str:
    # 配置删除后不再显示“在配”；历史采集仍保留。
    with patch_source(fetch_rules=[kept_rule]):
        await sync.run(days=1, tasks_only=True)
    async with SessionLocal() as s:
        assert not (await repo.get_task(s, site_key=site_key("", "验收乙网站"), tag="通知")).in_rules
        assert await repo.get_task(s, site_key=site_key("", "验收丙网站"), tag="政策") is None
    # 重算源端空日期，旧分组必须消失。
    with patch_source(fetch_rules=[kept_rule], fetch_day=[]):
        await sync.run(days=1, tasks_only=False, use_watermark=False)
    async with SessionLocal() as s:
        assert (await repo.day_totals(s, today))["rows"] == 0
        assert await repo.get_task(s, site_key=site_key("", "验收乙网站"), tag="通知") is None
    return "removed rules and stale health cleanup / empty-day snapshot replacement"


async def check_failure_is_recorded() -> str:
    # 水位查询阶段失败也必须有同步记录。
    with patch_source(fetch_affected_days={"side_effect": OSError("acceptance: source unavailable")}):
        try:
            await sync.run(days=1, tasks_only=False)
        except OSError:
            pass
        else:
            raise AssertionError("expected source failure")
    async with SessionLocal() as s:
        assert (await repo.last_sync(s)).status == "failed"
        assert (await repo.last_successful_sync(s)).status == "success"
    return "source probe failure persisted / last success retained"


async def check_concurrent_exclusion() -> str:
    # 会话级锁不会被每日 commit 释放。
    async with engine.connect() as c:
        await c.execute(text("SELECT pg_advisory_lock(:key)"), {"key": SYNC_LOCK_KEY})
        await c.commit()
        try:
            try:
                await sync.run(days=1, tasks_only=True)
            except RuntimeError as exc:
                assert "已有爬虫同步" in str(exc)
            else:
                raise AssertionError("concurrent sync was allowed")
        finally:
            await c.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SYNC_LOCK_KEY})
            await c.commit()
    return "concurrent sync exclusion"


QA_NAMES = ["验收·省发展和改革委员会", "验收·市财政局", "验收·市商务局", "验收·市科技局"]
QA_TAGS = [
    "政策文件",
    "通知公告",
    "政策解读",
    "政府信息公开",
    "惠企政策",
    "专项资金申报",
    "公开目录 > 财政预决算与重大项目建设信息",
]


def qa_day(today: date, day: date) -> list[dict]:
    """四种停更程度轮流分配给各任务，周末不出数，覆盖全部健康状态。"""

    age = (today - day).days
    data = []
    for n, name in enumerate(QA_NAMES):
        for t, tag in enumerate(QA_TAGS):
            last_age = (1, 12, 40, 999)[(n + t) % 4]
            if age >= last_age and age % 7 not in (0, 6):
                data.append(daily(day, name, tag, (n + 1) * 3 + (t + 1) * 2 + age % 5))
    return data


async def check_seeded_fixture(today: date) -> str:
    # 独立的验收数据，不复制旧业务库；覆盖分页、空编码、多状态和长标签。
    rules = [rule(name, tag, "" if i % 2 else f"QA{i:03}") for i, name in enumerate(QA_NAMES) for tag in QA_TAGS]
    with patch_source(fetch_rules=rules, fetch_day={"side_effect": lambda day: qa_day(today, day)}):
        await sync.run(days=90, tasks_only=False, use_watermark=False)
    async with SessionLocal() as s:
        assert await repo.count_filtered(s, {}) == len(rules)
        distribution = await repo.health_distribution(s)
        assert set(distribution) == {"normal", "watch", "broken", "never"}
        for status in distribution:
            page, total = await repo.list_items(s, filters={"health_status": status}, page=1, page_size=100)
            exported = await repo.list_filtered(s, {"health_status": status})
            assert len(page) == total == len(exported)
        assert len(await repo.daily_trend(s, 90)) == 90
    return "seeded independent QA fixture / four statuses / export parity"


async def main() -> None:
    today = datetime.now(BEIJING).date()
    rules = [rule("验收甲网站", "通知", "A"), rule("验收乙网站", "通知"), rule("验收丙网站", "政策")]
    # 顺序有依赖：后面的步骤基于前面留下的数据和同步记录。
    results = [
        await check_empty_database(),
        await check_first_sync(today, rules),
        await check_removed_rules(today, rules[0]),
        await check_failure_is_recorded(),
        await check_concurrent_exclusion(),
        await check_seeded_fixture(today),
    ]
    fixture_tasks = len(QA_NAMES) * len(QA_TAGS)
    print(
        json.dumps(
            {"passed": results, "fixture_tasks": fixture_tasks, "database": engine.url.database}, ensure_ascii=False
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
