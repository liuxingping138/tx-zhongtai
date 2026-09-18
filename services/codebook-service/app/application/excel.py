from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from platform_common.errors import ApiError, ErrorCode

from app.core.clock import format_beijing
from app.domain.fields import (
    AUDIT_EXPORT_COLUMNS,
    ColumnSpec,
    header_to_field,
)


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
    sheet = book[sheet_name] if sheet_name and sheet_name in book.sheetnames else book[book.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    mapping: list[str | None] = []
    for header_row in rows:
        if header_row is None or all(cell is None or str(cell).strip() == "" for cell in header_row):
            continue
        mapping = [header_to_field(columns, str(cell or "")) for cell in header_row]
        if any(mapping):
            break
        raise ApiError("Excel 表头与码表字段不匹配", code=ErrorCode.VALIDATION_ERROR, http_status=422)
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
            if spec.field in {"created_at", "updated_at"}:
                values.append(format_beijing(value))
            else:
                values.append("" if value is None else str(value))
        sheet.append(values)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


SKIP_REASON_COLUMN = ColumnSpec("skip_reason", "跳过原因")


def encode_skipped_file(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str = "跳过明细",
) -> str | None:
    if not rows:
        return None
    payload = build_workbook((*columns, SKIP_REASON_COLUMN), rows, sheet_name=sheet_name, include_audit=False)
    return base64.standard_b64encode(payload).decode("ascii")
