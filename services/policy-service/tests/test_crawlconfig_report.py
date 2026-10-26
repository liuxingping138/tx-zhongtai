"""爬虫配置统计的口径：自然周、统计起始周之前算期初存量、累计上线，分省每周配置数，以及导出的 Excel。"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.crawlconfig.application.report_excel import build_report_workbook
from app.crawlconfig.domain import report as rules


def test_periods_are_natural_weeks_months_quarters_and_years() -> None:
    friday = date(2026, 10, 23)
    assert rules.period_start(friday, "week") == date(2026, 10, 19)
    assert rules.period_end(date(2026, 10, 26), "week") == date(2026, 11, 1)  # 周日
    assert rules.period_start(friday, "month") == date(2026, 10, 1)
    assert rules.period_end(date(2026, 2, 1), "month") == date(2026, 2, 28)
    assert (rules.period_start(friday, "quarter"), rules.period_end(date(2026, 10, 1), "quarter")) == (
        date(2026, 10, 1),
        date(2026, 12, 31),
    )
    assert rules.period_start(friday, "year") == date(2026, 1, 1)
    assert rules.shift(date(2026, 1, 15), "quarter", -1) == date(2025, 10, 1)
    assert rules.shift(date(2026, 11, 3), "month", 2) == date(2027, 1, 1)


def test_default_is_last_week_but_the_current_month_quarter_and_year() -> None:
    monday = date(2026, 10, 26)
    assert rules.default_period(monday, "week") == date(2026, 10, 19)
    assert rules.default_period(monday, "month") == date(2026, 10, 1)
    assert rules.default_period(monday, "quarter") == date(2026, 10, 1)
    assert rules.default_period(monday, "year") == date(2026, 1, 1)


def test_window_ends_at_the_current_period_and_years_start_from_the_first_data() -> None:
    today = date(2026, 10, 26)
    weeks = rules.window(today, "week", None)
    assert (len(weeks), weeks[0], weeks[-1]) == (12, date(2026, 8, 10), date(2026, 10, 26))
    assert rules.window(today, "year", date(2023, 5, 1)) == [
        date(2023, 1, 1),
        date(2024, 1, 1),
        date(2025, 1, 1),
        date(2026, 1, 1),
    ]
    assert rules.window(today, "year", None) == [date(2017 + offset, 1, 1) for offset in range(10)]


def test_months_and_quarters_are_this_whole_year_including_the_ones_not_yet_reached() -> None:
    today = date(2026, 10, 26)
    assert rules.window(today, "month", None) == [date(2026, month, 1) for month in range(1, 13)]
    assert rules.window(today, "quarter", None) == [date(2026, month, 1) for month in (1, 4, 7, 10)]


def test_series_and_previous_count_add_up_days_in_each_period() -> None:
    daily = {"2026-09-30": 5, "2026-10-01": 3, "2026-10-31": 1, "2026-11-10": 4, "坏日期": 9}
    starts = [date(2026, 10, 1), date(2026, 11, 1)]
    assert rules.series(daily, starts, "month") == [
        {"period_from": "2026-10-01", "period_to": "2026-10-31", "new": 4},
        {"period_from": "2026-11-01", "period_to": "2026-11-30", "new": 4},
    ]
    assert rules.count_between(daily, date(2026, 9, 1), date(2026, 9, 30)) == 5


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


def test_workbook_opens_with_the_province_table_leaders_read() -> None:
    """第一张就是每周汇报那张：这期有配置的省份按数量从多到少，末行总计。公式样的文字保持文本。"""

    status = [
        {"province_name": "北京市", "total": 3, "online": 2, "pending": 1, "abnormal": 0},
        {"province_name": "河北省", "total": 5, "online": 5, "pending": 0, "abnormal": 0},
    ]
    data = {
        "period_from": "2026-10-19",
        "period_to": "2026-10-25",
        "backfill_date": "2026-10-22",
        "baseline": 10,
        "new": 5,
        "provinces": [{"province_name": "河北省", "new": 3}, {"province_name": "北京市", "new": 2}],
        "status": status,
        "totals": {"total": 8, "online": 7, "pending": 1, "abnormal": 0, "coverage": 87.5},
        "periods": [{"period_from": "2026-10-19", "period_to": "2026-10-25", "new": 5}],
        "new_sites": [_site('=HYPERLINK("x")', "11000000001"), _site("北京市人民政府", "11000000002")],
    }
    book = load_workbook(BytesIO(build_report_workbook(data, [_site("异常网站", "11000000003")])))
    assert book.sheetnames == ["配置数量", "配置明细", "分省爬虫状态", "配置趋势", "异常清单"]

    def rows(name: str) -> list[list[object]]:
        return [list(row) for row in book[name].iter_rows(min_row=2, values_only=True)]

    assert book["配置数量"]["A1"].value == "爬虫配置网站数量（2026-10-19 至 2026-10-25）"
    assert rows("配置数量") == [["省份", "配置网站数量"], ["河北省", 3], ["北京市", 2], ["总计", 5]]
    assert rows("分省爬虫状态") == [
        ["省份", "已爬", "未爬", "异常", "合计"],
        ["北京市", 2, 1, 0, 3],
        ["河北省", 5, 0, 0, 5],
        ["总计", 7, 1, 0, 8],
    ]
    detail = book["配置明细"]
    assert detail["D3"].value == '=HYPERLINK("x")' and detail["D3"].data_type == "s"
    assert rows("配置趋势")[1] == ["2026-10-19", "2026-10-25", 5]
    assert book["异常清单"]["D3"].value == "异常网站"
