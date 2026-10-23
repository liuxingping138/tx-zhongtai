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


def test_export_keeps_text_exactly_and_drops_characters_xml_cannot_hold() -> None:
    values = ["  前后空格  ", "换行\n第二行", "回车\r\n换行", "<&>\"'", "😀 生僻字𠮷", "坏\x00字\x1f符"]
    rows = [{"site_name": value} for value in values]
    content = build_workbook(_COLUMNS, rows, sheet_name="信源", include_audit=False)
    sheet = load_workbook(BytesIO(content))["信源"]
    assert [cell.value for (cell,) in sheet.iter_rows(min_row=2)] == [*values[:-1], "坏字符"]


def test_export_skips_empty_cells_and_names_sheet_legally() -> None:
    columns = (*_COLUMNS, ColumnSpec("url", "链接"))
    content = build_workbook(columns, [{"site_name": "", "url": "u"}], sheet_name="a/b:c" * 10, include_audit=False)
    book = load_workbook(BytesIO(content))
    assert book.sheetnames == ["a_b_ca_b_ca_b_ca_b_ca_b_ca_b_ca"]
    assert list(book.active.values) == [("网站名称", "链接"), (None, "u")]


def test_export_bytes_are_stable_for_the_same_rows() -> None:
    rows = [{"site_name": f"网站{i}"} for i in range(2500)]
    first = build_workbook(_COLUMNS, rows, sheet_name="信源")
    assert first == build_workbook(_COLUMNS, rows, sheet_name="信源")
    assert len(parse_sheet(first, _COLUMNS)) == 2500
