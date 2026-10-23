"""爬虫配置统计的口径：自然周、统计起始周之前算期初存量、累计上线，分省每周配置数，以及导出的 Excel。"""

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


def test_province_weekly_counts_line_up_with_trend_weeks() -> None:
    weeks = [date(2026, 10, 26), date(2026, 11, 2)]
    rows = [
        ("广东省", "2026-10-27", 3),
        ("广东省", "2026-11-08", 2),
        ("", "2026-11-03", 1),
        ("广东省", "2026-10-20", 9),  # 不在这两周
        ("北京市", "坏日期", 4),
    ]
    assert rules.province_weekly(rows, weeks) == {"广东省": [3, 2], rules.BLANK_PROVINCE: [0, 1]}


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


def test_workbook_opens_with_the_weekly_province_table_leaders_read() -> None:
    """第一张就是每周汇报那张：本周有配置的省份按数量从多到少，末行总计。公式样的文字保持文本。"""

    beijing = {"total": 3, "online": 2, "pending": 1, "abnormal": 0, "new": 2, "coverage": 66.7}
    hebei = {"total": 5, "online": 5, "pending": 0, "abnormal": 0, "new": 3, "coverage": 100.0}
    hubei = {"total": 1, "online": 0, "pending": 1, "abnormal": 0, "new": 0, "coverage": 0.0}
    totals = {"total": 9, "online": 7, "pending": 2, "abnormal": 0, "new": 5, "coverage": 77.8}
    data = {
        "week_from": "2026-10-26",
        "week_to": "2026-11-01",
        "report_start": "2026-10-23",
        "counted": True,
        "baseline": 10,
        "provinces": [
            {"province_name": "北京市", **beijing, "weekly": [2]},
            {"province_name": "河北省", **hebei, "weekly": [3]},
            {"province_name": "湖北省", **hubei, "weekly": [0]},
        ],
        "totals": totals,
        "trend": [{"week_from": "2026-10-26", "week_to": "2026-11-01", "new": 5, "cumulative": 15}],
        "new_sites": [_site('=HYPERLINK("x")', "11000000001"), _site("北京市人民政府", "11000000002")],
    }
    book = load_workbook(BytesIO(build_report_workbook(data, [_site("异常网站", "11000000003")])))
    assert book.sheetnames == ["本周配置数量", "分省每周配置", "分省累计", "本周新增明细", "每周趋势", "异常清单"]

    def rows(name: str) -> list[list[object]]:
        return [list(row) for row in book[name].iter_rows(min_row=2, values_only=True)]

    assert book["本周配置数量"]["A1"].value == "爬虫配置网站数量（2026-10-26 至 2026-11-01）"
    assert rows("本周配置数量") == [["省份", "配置网站数量"], ["河北省", 3], ["北京市", 2], ["总计", 5]]
    assert rows("分省每周配置")[-1] == ["总计", 5, 5]
    assert rows("分省累计")[-1] == ["总计", 9, 7, 2, 0, "77.8%"]
    detail = book["本周新增明细"]
    assert detail["D3"].value == '=HYPERLINK("x")' and detail["D3"].data_type == "s"
    assert [row[2] for row in book["每周趋势"].iter_rows(min_row=3, values_only=True)] == [5]
    assert book["异常清单"]["D3"].value == "异常网站"
