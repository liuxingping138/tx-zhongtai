"""爬虫配置统计的 Excel，给领导看：第一张就是每周汇报用的「省份 / 配置网站数量 / 总计」，
后面是这期配置明细、分省爬虫状态、各期趋势、异常清单。每张第一行标题、第二行表头。"""

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
    ("tag", "栏目", 24),
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


def _period_sheet(sheet: Worksheet, data: dict[str, Any], period: str) -> None:
    """领导每周看的那张：这一期有配置的省份，按配置网站数量从多到少，末行总计。"""

    _sheet(sheet, "配置数量", f"爬虫配置网站数量（{period}）", [("省份", 18), ("配置网站数量", 14)])
    for row in data["provinces"]:
        append_text_row(sheet, [row["province_name"], row["new"]])
    append_text_row(sheet, ["总计", data["new"]])
    _bold_last_row(sheet, 2)


def _status_sheet(book: Workbook, data: dict[str, Any]) -> None:
    """信源表按省透视爬虫状态，末行总计。"""

    headers = [("省份", 16), ("已爬", 10), ("未爬", 10), ("异常", 10), ("合计", 10)]
    caption = f"各省爬虫状态（截至导出时，{format_beijing(utcnow())}）"
    sheet = _sheet(book.create_sheet(), "分省爬虫状态", caption, headers)
    for row in [*data["status"], {**data["totals"], "province_name": "总计"}]:
        append_text_row(sheet, [row[key] for key in ("province_name", "online", "pending", "abnormal", "total")])
    _bold_last_row(sheet, len(headers))


def build_report_workbook(data: dict[str, Any], abnormal: list[dict[str, Any]]) -> bytes:
    period = f"{data['period_from']} 至 {data['period_to']}"
    book = Workbook()
    _period_sheet(active_worksheet(book), data, period)
    _site_sheet(book, "配置明细", f"这期配置的网站（{period}），共 {len(data['new_sites'])} 个", data["new_sites"])
    _status_sheet(book, data)
    trend = _sheet(
        book.create_sheet(),
        "配置趋势",
        f"各期配置网站数量（{data['backfill_date']} 统一补填上线时间的 {data['baseline']} 个算期初，不计入任何一期）",
        [("开始", 12), ("结束", 12), ("配置网站数量", 14)],
    )
    for item in data["periods"]:
        append_text_row(trend, [item["period_from"], item["period_to"], item["new"]])
    _site_sheet(book, "异常清单", f"爬虫状态为异常的网站，共 {len(abnormal)} 个，请业务核对", abnormal)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
