"""导出的 Excel 不能带活公式。"""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook

from platform_common.columns import ColumnSpec
from platform_common.excel import build_workbook, parse_sheet

_COLUMNS = (ColumnSpec("site_name", "网站名称"),)
_PAYLOAD = '=HYPERLINK("http://example.invalid","点我")'


@pytest.mark.parametrize(
    "payload",
    [
        _PAYLOAD,
        "+1+1",
        "-1+1",
        "@SUM(1+1)",
        "\t=1+1",
    ],
)
def test_export_writes_formula_like_values_as_text(payload: str) -> None:
    content = build_workbook(_COLUMNS, [{"site_name": payload}], sheet_name="信源", include_audit=False)
    cell = load_workbook(BytesIO(content))["信源"]["A2"]
    assert cell.data_type == "s"
    assert cell.value == payload


def test_export_round_trips_through_import_unchanged() -> None:
    content = build_workbook(_COLUMNS, [{"site_name": _PAYLOAD}], sheet_name="信源", include_audit=False)
    assert parse_sheet(content, _COLUMNS)[0]["site_name"] == _PAYLOAD
