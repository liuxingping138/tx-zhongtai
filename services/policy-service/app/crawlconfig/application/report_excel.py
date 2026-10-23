"""爬虫配置统计的 Excel：分省汇总、分省每周配置、本周新增明细、每周趋势、异常清单。给领导看，带标题行和列宽。"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from platform_common.clock import format_beijing, utcnow
from platform_common.excel import active_worksheet, append_text_row

SITE_HEADERS = (
    ("province_name", "省份", 12),
    ("city_name", "地市", 12),
    ("district_name", "区县", 12),
    ("site_name", "网站名称", 36),
    ("site_code", "网站编码", 16),
    ("url", "链接", 48),
    ("crawler_status", "爬虫状态", 10),
    ("online_date", "上线时间", 12),
)
_BOLD = Font(bold=True)


def _sheet(sheet: Worksheet, title: str, caption: str, headers: list[tuple[str, int]]) -> Worksheet:
    """第一行标题、第二行表头（加粗、冻结），列宽按内容定。"""

    sheet.title = title
    append_text_row(sheet, [caption])
    sheet.cell(row=1, column=1).font = Font(bold=True, size=13)
    append_text_row(sheet, [name for name, _ in headers])
    for index, (_, width) in enumerate(headers, start=1):
        sheet.cell(row=2, column=index).font = _BOLD
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A3"
    return sheet


def _site_sheet(book: Workbook, title: str, caption: str, sites: list[dict[str, Any]]) -> None:
    sheet = _sheet(book.create_sheet(), title, caption, [(name, width) for _, name, width in SITE_HEADERS])
    for site in sites:
        append_text_row(sheet, [site.get(key, "") for key, _, _ in SITE_HEADERS])


def _province_weekly_sheet(book: Workbook, data: dict[str, Any]) -> None:
    """省份 × 周的新配置栏目数，末列合计、末行全国合计。统计起点之前的周没有这张表的数据。"""

    weeks = data["trend"]
    headers = [("省份", 16), *((f"{w['week_from'][5:]}至{w['week_to'][5:]}", 13) for w in weeks), ("合计", 10)]
    sheet = _sheet(
        book.create_sheet(), "分省每周配置", f"各省每周新配置上线的栏目数（统计起始周 {data['report_start']}）", headers
    )
    for row in data["provinces"]:
        weekly = row.get("weekly") or [0] * len(weeks)
        append_text_row(sheet, [row["province_name"], *weekly, sum(weekly)])
    totals = [w["new"] for w in weeks]
    append_text_row(sheet, ["合计", *totals, sum(totals)])
    for column in range(1, len(headers) + 1):
        sheet.cell(row=sheet.max_row, column=column).font = _BOLD


def build_report_workbook(data: dict[str, Any], abnormal: list[dict[str, Any]]) -> bytes:
    week = f"{data['week_from']} 至 {data['week_to']}"
    note = "" if data["counted"] else f"（统计从 {data['report_start']} 那周开始，本周不计新增）"
    book = Workbook()
    summary = _sheet(
        active_worksheet(book),
        "分省汇总",
        f"爬虫配置统计（{week}）{note}　导出时间 {format_beijing(utcnow())}",
        [("省份", 16), ("栏目总数", 10), ("已爬", 10), ("未爬", 10), ("异常", 10), ("本周新增", 10), ("覆盖率", 10)],
    )
    for row in [*data["provinces"], {**data["totals"], "province_name": "合计"}]:
        values = [row[key] for key in ("total", "online", "pending", "abnormal", "new")]
        append_text_row(summary, [row["province_name"], *values, f"{row['coverage']}%"])
    for column in range(1, 8):
        summary.cell(row=summary.max_row, column=column).font = _BOLD

    _province_weekly_sheet(book, data)
    _site_sheet(book, "本周新增明细", f"本周新增上线栏目（{week}），共 {len(data['new_sites'])} 个", data["new_sites"])

    trend = _sheet(
        book.create_sheet(),
        "每周趋势",
        f"每周新增上线栏目（期初存量 {data['baseline']} 个，统计起始周 {data['report_start']}）",
        [("周开始", 12), ("周结束", 12), ("新增上线", 10), ("累计上线", 10)],
    )
    for item in data["trend"]:
        append_text_row(trend, [item["week_from"], item["week_to"], item["new"], item["cumulative"]])

    _site_sheet(book, "异常清单", f"爬虫状态为异常的栏目，共 {len(abnormal)} 个，请业务核对", abnormal)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
