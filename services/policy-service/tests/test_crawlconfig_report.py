"""爬虫配置周报的口径：自然周、统计起始周之前算期初存量、累计上线，以及导出的 Excel 四个工作表。"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.crawlconfig.application.report_excel import build_report_workbook
from app.crawlconfig.domain import report as rules

START = date(2026, 10, 26)  # 周一


def test_weeks_run_monday_to_sunday() -> None:
    assert rules.week_start(date(2026, 10, 23)) == date(2026, 10, 19)  # 周五
    assert rules.week_start(date(2026, 10, 26)) == date(2026, 10, 26)
    assert rules.week_end(date(2026, 11, 1)) == date(2026, 11, 1)  # 周日


def test_trend_never_reaches_before_the_report_start_and_keeps_twelve_weeks_at_most() -> None:
    assert rules.trend_weeks(date(2026, 10, 23), START) == []
    assert rules.trend_weeks(date(2026, 11, 4), START) == [date(2026, 10, 26), date(2026, 11, 2)]
    weeks = rules.trend_weeks(date(2027, 6, 1), START)
    assert len(weeks) == rules.TREND_WEEKS and weeks[-1] == date(2027, 5, 31)


def test_weekly_series_adds_baseline_and_weeks_before_the_window_to_the_cumulative() -> None:
    weeks = [date(2026, 11, 2), date(2026, 11, 9)]
    daily = {"2026-10-27": 5, "2026-11-02": 3, "2026-11-08": 1, "2026-11-10": 4, "坏日期": 9}
    assert rules.weekly_series(daily, weeks, baseline=100) == [
        {"week_from": "2026-11-02", "week_to": "2026-11-08", "new": 4, "cumulative": 109},
        {"week_from": "2026-11-09", "week_to": "2026-11-15", "new": 4, "cumulative": 113},
    ]
    assert rules.weekly_series(daily, [], baseline=100) == []


def test_provinces_follow_codes_then_uncoded_then_blank() -> None:
    rows = [
        {"province_name": "", "province_code": None},
        {"province_name": "国家", "province_code": None},
        {"province_name": "河北省", "province_code": "13"},
        {"province_name": "北京市", "province_code": "11"},
    ]
    assert [row["province_name"] for row in sorted(rows, key=rules.province_order)] == ["北京市", "河北省", "国家", ""]
    assert (rules.coverage(1, 3), rules.coverage(0, 0)) == (33.3, 0.0)


def _site(name: str, code: str) -> dict[str, Any]:
    return {
        "province_name": "北京市",
        "site_name": name,
        "site_code": code,
        "crawler_status": "已爬",
        "online_date": "2026-10-27",
    }


def test_workbook_has_four_sheets_with_totals_and_keeps_formula_like_text_as_text() -> None:
    counts = {"total": 3, "online": 2, "pending": 1, "abnormal": 0, "new": 2, "coverage": 66.7}
    data = {
        "week_from": "2026-10-26",
        "week_to": "2026-11-01",
        "report_start": "2026-10-26",
        "counted": True,
        "baseline": 10,
        "provinces": [{"province_name": "北京市", **counts}],
        "totals": counts,
        "trend": [{"week_from": "2026-10-26", "week_to": "2026-11-01", "new": 2, "cumulative": 12}],
        "new_sites": [_site('=HYPERLINK("x")', "11000000001"), _site("北京市人民政府", "11000000002")],
    }
    book = load_workbook(BytesIO(build_report_workbook(data, [_site("异常网站", "11000000003")])))
    assert book.sheetnames == ["分省汇总", "本周新增明细", "每周趋势", "异常清单"]
    summary = [list(row) for row in book["分省汇总"].iter_rows(min_row=2, values_only=True)]
    assert summary == [
        ["省份", "栏目总数", "已爬", "未爬", "异常", "本周新增", "覆盖率"],
        ["北京市", 3, 2, 1, 0, 2, "66.7%"],
        ["合计", 3, 2, 1, 0, 2, "66.7%"],
    ]
    detail = book["本周新增明细"]
    assert detail["D3"].value == '=HYPERLINK("x")' and detail["D3"].data_type == "s"
    assert [row[2] for row in book["每周趋势"].iter_rows(min_row=3, values_only=True)] == [2]
    assert book["异常清单"]["D3"].value == "异常网站"
