"""导出的 Excel 不能带活公式。"""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from platform_common.columns import ColumnSpec
from platform_common.excel import build_workbook, parse_sheet

_COLUMNS = (ColumnSpec("site_name", "网站名称"),)
_PAYLOAD = '=HYPERLINK("http://example.invalid","点我")'


def test_export_writes_formula_like_values_as_text() -> None:
    content = build_workbook(_COLUMNS, [{"site_name": _PAYLOAD}], sheet_name="信源", include_audit=False)
    cell = load_workbook(BytesIO(content))["信源"]["A2"]
    assert cell.data_type == "s"
    assert cell.value == _PAYLOAD


def test_export_round_trips_through_import_unchanged() -> None:
    content = build_workbook(_COLUMNS, [{"site_name": _PAYLOAD}], sheet_name="信源", include_audit=False)
    assert parse_sheet(content, _COLUMNS)[0]["site_name"] == _PAYLOAD
