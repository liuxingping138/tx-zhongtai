"""爬虫监测的字段与筛选约定。

页面和导出共用同一份行结构，列清单漏了字段不会报错、只会悄悄少一列，
所以这里把 `_to_out` 的输出键和导出列定义对死。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.crawler.application.crawler import _to_out
from app.crawler.domain.fields import CRAWLER_TASK_COLUMNS, HEALTH_STATUS_LABELS
from app.crawler.domain.models import CrawlerTaskHealth
from app.crawler.repositories import crawler as repo


def _row(**overrides: object) -> CrawlerTaskHealth:
    row = CrawlerTaskHealth(
        id=uuid.uuid4(),
        site_code="62110000001",
        site_name="定西市人民政府",
        province_name="甘肃省",
        city_name="定西市",
        tag="政策>法定主动公开内容>政策文件>规范性文件",
        source_url="http://www.dingxi.gov.cn/col/col15851/index.html",
        last_collect_date=date(2026, 9, 20),
        stale_days=2,
        count_7d=3,
        count_30d=11,
        count_90d=40,
        count_total=70,
        health_status="normal",
        in_rules=True,
        computed_at=datetime(2026, 9, 22, 1, 0, tzinfo=UTC),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_export_columns_exist_in_row_payload() -> None:
    payload = _to_out(_row())
    missing = [spec.field for spec in CRAWLER_TASK_COLUMNS if spec.field not in payload]
    assert not missing, f"导出列在行数据里找不到：{missing}"


def test_every_health_status_has_a_chinese_label() -> None:
    for status in ("normal", "watch", "broken", "never"):
        assert HEALTH_STATUS_LABELS[status]


def test_never_collected_row_reports_empty_date_not_epoch() -> None:
    payload = _to_out(_row(last_collect_date=None, stale_days=None, health_status="never"))
    assert payload["last_collect_date"] == ""
    assert payload["stale_days"] is None


def test_abnormal_only_covers_broken_and_never() -> None:
    """「异常清单」必须同时包含断爬和从未出数，少一类就会漏派单。"""

    assert set(repo.ABNORMAL_STATUSES) == {"broken", "never"}
    assert len(repo._conditions({"abnormal_only": True})) == 1


def test_status_and_stale_days_are_not_fuzzy_matched() -> None:
    """状态要精确相等、停更天数是数值下限，走模糊匹配会筛出错误结果。"""

    conds = repo._conditions({"health_status": "broken", "stale_days_min": 30})
    assert len(conds) == 2
    assert all("ilike" not in str(cond).lower() for cond in conds)


def test_unknown_filter_key_raises() -> None:
    with pytest.raises(KeyError):
        repo._conditions({"not_a_column": "x"})


def test_blank_filter_values_are_ignored() -> None:
    assert repo._conditions({"province_name": "", "health_status": None}) == []
