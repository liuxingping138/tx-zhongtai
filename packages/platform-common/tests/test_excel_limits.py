"""Excel 解压、行列和并发上限。"""

from __future__ import annotations

import asyncio
import io

import pytest
from openpyxl import Workbook

from platform_common.columns import ColumnSpec
from platform_common.errors import ApiError
from platform_common.excel import _parse_limiter, parse_sheet, parse_sheet_async

_COLUMNS = (ColumnSpec("site_name", "网站名称"),)


def _sheet(rows: int) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["网站名称"])
    for index in range(rows):
        sheet.append([f"站点{index}"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_row_limit_rejects_extra_data_row() -> None:
    with pytest.raises(ApiError, match="行数超过上限"):
        parse_sheet(_sheet(3), _COLUMNS, max_rows=2)


def test_uncompressed_bytes_are_rejected() -> None:
    with pytest.raises(ApiError, match="解压后过大"):
        parse_sheet(_sheet(1), _COLUMNS, max_uncompressed_bytes=32)


def test_parse_concurrency_is_two() -> None:
    assert _parse_limiter.total_tokens == 2


def test_async_parse_still_returns_rows() -> None:
    rows = asyncio.run(parse_sheet_async(_sheet(1), _COLUMNS))
    assert rows[0]["site_name"] == "站点0"


def test_sparse_rows_rejected_before_iteration() -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["网站名称"])
    sheet.cell(100003, 1, "远处数据")
    buffer = io.BytesIO()
    book.save(buffer)
    with pytest.raises(ApiError, match="行数超过上限"):
        parse_sheet(buffer.getvalue(), _COLUMNS)


@pytest.mark.parametrize("dimension", [b'<dimension ref="A1:A1"/>', b""])
def test_false_or_missing_dimension_cannot_hide_wide_cells(dimension: bytes) -> None:
    import re
    import zipfile

    book = Workbook()
    sheet = book.active
    sheet.append(["网站名称"])
    sheet.cell(2, 129, "超宽")
    raw = io.BytesIO()
    book.save(raw)
    fixed = io.BytesIO()
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(fixed, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "xl/worksheets/sheet1.xml":
                data = re.sub(rb"<dimension[^>]*/>", dimension, data)
            dst.writestr(name, data)
    with pytest.raises(ApiError, match="列数超过上限"):
        parse_sheet(fixed.getvalue(), _COLUMNS)


@pytest.mark.asyncio
async def test_resolve_and_import_share_actual_concurrency_budget() -> None:
    import threading
    import time

    from platform_common.excel import run_excel_parse

    lock = threading.Lock()
    running = peak = 0

    def work() -> None:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with lock:
            running -= 1

    await asyncio.gather(*(run_excel_parse(work) for _ in range(6)))
    assert peak == 2
