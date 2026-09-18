from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from platform_common.errors import ApiError, ErrorCode

from app.domain.fields import (
    AUDIT_EXPORT_COLUMNS,
    ColumnSpec,
    header_to_field,
)


def _pick_sheet(book: Any, sheet_name: str | None) -> Any:
    if sheet_name:
        if sheet_name in book.sheetnames:
            return book[sheet_name]
        stripped = {name.strip(): name for name in book.sheetnames}
        if sheet_name.strip() in stripped:
            return book[stripped[sheet_name.strip()]]
    return book[book.sheetnames[0]]


def parse_sheet(
    content: bytes,
    columns: tuple[ColumnSpec, ...],
    *,
    sheet_name: str | None = None,
) -> list[dict[str, str]]:
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("无法读取 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    sheet = _pick_sheet(book, sheet_name)
    rows = sheet.iter_rows(values_only=True)
    mapping: list[str | None] = []
    for header_row in rows:
        if header_row is None or all(cell is None or str(cell).strip() == "" for cell in header_row):
            continue
        mapping = [header_to_field(columns, str(cell or "")) for cell in header_row]
        if any(mapping):
            break
        raise ApiError("Excel 表头与政策字段不匹配", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    else:
        raise ApiError("Excel 为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    items: list[dict[str, str]] = []
    for raw in rows:
        if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
            continue
        item = {spec.field: "" for spec in columns}
        for idx, field in enumerate(mapping):
            if not field or idx >= len(raw):
                continue
            value = raw[idx]
            item[field] = "" if value is None else str(value).strip()
        items.append(item)
    return items


def build_workbook(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str,
    include_audit: bool = True,
) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = sheet_name[:31]
    export_cols = (*columns, *AUDIT_EXPORT_COLUMNS) if include_audit else columns
    sheet.append([spec.header for spec in export_cols])
    for row in rows:
        values = []
        for spec in export_cols:
            value = row.get(spec.field)
            isoformat = getattr(value, "isoformat", None)
            if callable(isoformat):
                values.append(str(isoformat()).replace("+00:00", "Z"))
            else:
                values.append("" if value is None else str(value))
        sheet.append(values)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
