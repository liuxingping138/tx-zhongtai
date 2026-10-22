"""读模板 Excel：第一行是表头，之后每行一条待提问数据，所有值按文本处理。

openpyxl 是同步 CPU 计算，调用方一律经 run_excel_parse 放到线程池。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import iter_workbook_rows

from app.core.storage import PROMPT_FILES, ROWS_FILE

CODE_ENCODINGS = ("utf-8-sig", "gbk")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _headers(raw: tuple[Any, ...]) -> list[str]:
    """空表头补成「列N」，重名补「.1」「.2」，和旧系统 pandas 读出来的列名一致。"""

    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, value in enumerate(raw, 1):
        name = _text(value).strip() or f"列{index}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        headers.append(f"{name}.{count}" if count else name)
    return headers


def read_sheet(content: bytes, *, limit: int | None = None) -> tuple[list[str], list[dict[str, str]]]:
    """返回 (表头, 数据行)。整行为空的跳过；limit 给定时只读前 limit 条数据。"""

    rows = iter_workbook_rows(content)
    try:
        first = next(rows, None)
        if first is None:
            raise ApiError("Excel 没有表头", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        headers = _headers(first)
        data: list[dict[str, str]] = []
        for values in rows:
            texts = [_text(value) for value in values]
            if not any(item.strip() for item in texts):
                continue
            data.append({name: texts[index] if index < len(texts) else "" for index, name in enumerate(headers)})
            if limit is not None and len(data) >= limit:
                break
        return headers, data
    finally:
        rows.close()


def sheet_summary(content: bytes) -> tuple[list[str], int]:
    headers, data = read_sheet(content)
    if not data:
        raise ApiError("Excel 没有数据行", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return headers, len(data)


def decode_code_table(content: bytes) -> str:
    """码表常是 Windows 下另存的 txt，依次试 UTF-8 和 GBK。"""

    for encoding in CODE_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError("码表编码无法识别，请另存为 UTF-8 文本", code=ErrorCode.VALIDATION_ERROR, http_status=422)


def read_run_input(run_dir: Path) -> tuple[list[str], list[dict[str, str]]]:
    """任务的输入快照：流水线任务是 rows.json（不受 Excel 单元格上限限制），页面发起的是 source.xlsx。"""

    rows_file = run_dir / ROWS_FILE
    if rows_file.is_file():
        data = json.loads(rows_file.read_text(encoding="utf-8"))
        return list(data["headers"]), [dict(row) for row in data["rows"]]
    excel = run_dir / PROMPT_FILES["excel"]
    if not excel.is_file():
        raise RuntimeError("任务的输入快照不存在")
    return read_sheet(excel.read_bytes())


def has_run_input(run_dir: Path) -> bool:
    return (run_dir / ROWS_FILE).is_file() or (run_dir / PROMPT_FILES["excel"]).is_file()
