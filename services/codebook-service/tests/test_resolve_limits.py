from io import BytesIO

import pytest
from openpyxl import Workbook
from platform_common.errors import ApiError

from app.application.area_resolve import build_resolve_workbook


@pytest.mark.parametrize("row,col", [(2, 129), (100003, 1)])
def test_resolve_rejects_oversized_sheet(row: int, col: int) -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["省份名称"])
    sheet.cell(row, col, "广东省")
    buf = BytesIO()
    book.save(buf)
    with pytest.raises(ApiError, match="超过上限"):
        build_resolve_workbook(buf.getvalue(), [])
