"""爬虫配置统计的 Excel，给领导看：第一张就是每周汇报用的「省份 / 配置网站数量 / 总计」，
后面是分省每周配置、分省累计、本周新增明细、每周趋势、异常清单。每张第一行标题、第二行表头。"""

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


def _bold_last_row(sheet: Worksheet, columns: int) -> None:
    for column in range(1, columns + 1):
        sheet.cell(row=sheet.max_row, column=column).font = _BOLD


def _site_sheet(book: Workbook, title: str, caption: str, sites: list[dict[str, Any]]) -> None:
    sheet = _sheet(book.create_sheet(), title, caption, [(name, width) for _, name, width in SITE_HEADERS])
    for site in sites:
        append_text_row(sheet, [site.get(key, "") for key, _, _ in SITE_HEADERS])


def _week_sheet(sheet: Worksheet, data: dict[str, Any], week: str) -> None:
    """领导每周看的那张：本周有配置的省份，按配置网站数量从多到少，末行总计。"""

    _sheet(sheet, "本周配置数量", f"爬虫配置网站数量（{week}）", [("省份", 18), ("配置网站数量", 14)])
    rows = sorted((row for row in data["provinces"] if row["new"]), key=lambda row: -row["new"])
    for row in rows:
        append_text_row(sheet, [row["province_name"], row["new"]])
    append_text_row(sheet, ["总计", data["totals"]["new"]])
    _bold_last_row(sheet, 2)


def _province_weekly_sheet(book: Workbook, data: dict[str, Any]) -> None:
    """省份 × 周的配置网站数量，末列合计、末行总计。统计起点之前的周没有数据。"""

    weeks = data["trend"]
    headers = [("省份", 16), *((f"{w['week_from'][5:]}至{w['week_to'][5:]}", 13) for w in weeks), ("合计", 10)]
    caption = "各省每周配置网站数量（近 12 周，最后一列是所选这周）"
    sheet = _sheet(book.create_sheet(), "分省每周配置", caption, headers)
    for row in data["provinces"]:
        weekly = row.get("weekly") or [0] * len(weeks)
        append_text_row(sheet, [row["province_name"], *weekly, sum(weekly)])
    totals = [w["new"] for w in weeks]
    append_text_row(sheet, ["总计", *totals, sum(totals)])
    _bold_last_row(sheet, len(headers))


def _province_total_sheet(book: Workbook, data: dict[str, Any]) -> None:
    headers = [("省份", 16), ("信源网站数", 12), ("已配置", 10), ("未配置", 10), ("异常", 10), ("覆盖率", 10)]
    sheet = _sheet(
        book.create_sheet(), "分省累计", f"各省累计配置情况（截至导出时，{format_beijing(utcnow())}）", headers
    )
    for row in [*data["provinces"], {**data["totals"], "province_name": "总计"}]:
        values = [row[key] for key in ("total", "online", "pending", "abnormal")]
        append_text_row(sheet, [row["province_name"], *values, f"{row['coverage']}%"])
    _bold_last_row(sheet, len(headers))


def build_report_workbook(data: dict[str, Any], abnormal: list[dict[str, Any]]) -> bytes:
    week = f"{data['week_from']} 至 {data['week_to']}"
    book = Workbook()
    _week_sheet(active_worksheet(book), data, week)
    _province_weekly_sheet(book, data)
    _province_total_sheet(book, data)
    _site_sheet(book, "本周新增明细", f"本周新配置的网站（{week}），共 {len(data['new_sites'])} 个", data["new_sites"])
    trend = _sheet(
        book.create_sheet(),
        "每周趋势",
        f"每周配置网站数量（{data['backfill_date']} 统一补填上线时间的 {data['baseline']} 个算期初存量）",
        [("周开始", 12), ("周结束", 12), ("当周配置", 10), ("累计已配置", 12)],
    )
    for item in data["trend"]:
        append_text_row(trend, [item["week_from"], item["week_to"], item["new"], item["cumulative"]])
    _site_sheet(book, "异常清单", f"爬虫状态为异常的网站，共 {len(abnormal)} 个，请业务核对", abnormal)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
