from __future__ import annotations

import base64
from functools import partial
from io import BytesIO
from typing import Any

from anyio import to_thread
from openpyxl import Workbook, load_workbook
from platform_common.errors import ApiError, ErrorCode

from app.core.clock import format_beijing
from app.domain.fields import (
    AUDIT_EXPORT_COLUMNS,
    ColumnSpec,
    header_to_field,
)


def _field_of(columns: tuple[ColumnSpec, ...], header: str) -> str | None:
    raw = (header or "").replace("\n", " ").strip()
    if raw in {"校验说明", "跳过原因"}:
        return "skip_reason"
    return header_to_field(columns, header)


def parse_sheet(
    content: bytes,
    columns: tuple[ColumnSpec, ...],
    *,
    sheet_name: str | None = None,
) -> list[dict[str, str]]:
    del sheet_name  # 上传只读第一个 sheet，不看名称
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("无法读取 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    sheet = book[book.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    mapping: list[str | None] = []
    parse_columns = (*columns, SKIP_REASON_COLUMN)
    for header_row in rows:
        if header_row is None or all(cell is None or str(cell).strip() == "" for cell in header_row):
            continue
        mapping = [_field_of(columns, str(cell or "")) for cell in header_row]
        if any(mapping):
            break
        raise ApiError("Excel 表头与码表字段不匹配", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    else:
        raise ApiError("Excel 为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    items: list[dict[str, str]] = []
    for raw in rows:
        if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
            continue
        item = {spec.field: "" for spec in parse_columns}
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


SKIP_REASON_COLUMN = ColumnSpec("skip_reason", "校验说明")


def encode_skipped_file(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str = "全部数据",
) -> str | None:
    if not rows:
        return None
    payload = build_workbook((*columns, SKIP_REASON_COLUMN), rows, sheet_name=sheet_name, include_audit=False)
    return base64.standard_b64encode(payload).decode("ascii")


# openpyxl 读写是纯 CPU 同步操作，直接在协程里跑会阻塞整个服务的事件循环
# （每个服务只有一个 uvicorn worker），大表导入导出期间所有请求都会被挂住。
# 下面三个 async 包装把它们放到线程池执行，行为与同步版本完全一致。


async def parse_sheet_async(
    content: bytes,
    columns: tuple[ColumnSpec, ...],
    *,
    sheet_name: str | None = None,
) -> list[dict[str, str]]:
    """在线程池中解析 Excel，避免阻塞事件循环。"""

    return await to_thread.run_sync(partial(parse_sheet, content, columns, sheet_name=sheet_name))


async def build_workbook_async(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str,
    include_audit: bool = True,
) -> bytes:
    """在线程池中生成 Excel，避免阻塞事件循环。"""

    return await to_thread.run_sync(
        partial(build_workbook, columns, rows, sheet_name=sheet_name, include_audit=include_audit)
    )


async def encode_skipped_file_async(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str = "全部数据",
) -> str | None:
    """在线程池中生成校验报告，避免阻塞事件循环。"""

    return await to_thread.run_sync(partial(encode_skipped_file, columns, rows, sheet_name=sheet_name))
