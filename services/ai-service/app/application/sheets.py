"""读模板 Excel：第一行是表头，之后每行一条待提问数据，所有值按文本处理。

openpyxl 是同步 CPU 计算，调用方一律经 run_excel_parse 放到线程池。
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import math
from collections.abc import Collection
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import active_worksheet, append_text_row, iter_workbook_rows

from app.core.storage import INPUT_LINES_FILE, PROMPT_FILES, ROWS_FILE, write_atomic

CODE_ENCODINGS = ("utf-8-sig", "gbk")


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        return str(value)
    if value.is_integer():
        return "0" if value == 0 else f"{value:.0f}"
    return format(Decimal(str(value)).normalize(), "f")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return _float_text(value)
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


def code_table_from_sheet(content: bytes) -> str:
    """Excel 码表转成文字：只读第一个工作表，一行一条、各格用 Tab 连起来（和系统码表发给模型的样子一样），空行跳过。"""

    rows = iter_workbook_rows(content)
    try:
        lines: list[str] = []
        for values in rows:
            texts = [_text(value).strip() for value in values]
            while texts and not texts[-1]:
                texts.pop()
            if texts:
                lines.append("\t".join(texts))
    finally:
        rows.close()
    if not lines:
        raise ApiError("Excel 码表的第一个工作表是空的", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return "\n".join(lines)


def decode_code_table(content: bytes) -> str:
    """码表常是 Windows 下另存的 txt，依次试 UTF-8 和 GBK。"""

    for encoding in CODE_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError("码表编码无法识别，请另存为 UTF-8 文本", code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _input_snapshot(run_dir: Path) -> Path:
    rows_file = run_dir / ROWS_FILE
    return rows_file if rows_file.is_file() else run_dir / PROMPT_FILES["excel"]


def read_run_input(run_dir: Path) -> tuple[list[str], list[dict[str, str]]]:
    """任务的输入快照：流水线任务是 rows.json（不受 Excel 单元格上限限制），页面发起的是 source.xlsx。"""

    snapshot = _input_snapshot(run_dir)
    if not snapshot.is_file():
        raise RuntimeError("任务的输入快照不存在")
    if snapshot.name == ROWS_FILE:
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        return list(data["headers"]), [dict(row) for row in data["rows"]]
    return read_sheet(snapshot.read_bytes())


def has_run_input(run_dir: Path) -> bool:
    return _input_snapshot(run_dir).is_file()


def _input_lines(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    """输入快照的逐行副本和它的首行（表头、行数）。首行记着快照的大小和修改时间，快照换了就重新生成。

    10 万行的用户 Excel 整个解析要 3 秒多，单是加载共享字符串表就近 2 秒；逐行副本取前 50 行不到 1 毫秒。
    """

    snapshot = _input_snapshot(run_dir)
    if not snapshot.is_file():
        raise RuntimeError("任务的输入快照不存在")
    stat = snapshot.stat()
    stamp = [stat.st_size, stat.st_mtime_ns]
    path = run_dir / INPUT_LINES_FILE
    head: dict[str, Any] | None = None
    with contextlib.suppress(OSError, ValueError), path.open(encoding="utf-8") as handle:
        head = json.loads(handle.readline())
    if head is None or head.get("snapshot") != stamp:
        headers, rows = read_run_input(run_dir)
        head = {"snapshot": stamp, "headers": headers, "rows": len(rows)}
        # json.dumps 把值里的换行转义成 \n：一条数据一定只占一行。
        lines = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in (head, *rows))
        write_atomic(path, lines.encode("utf-8"))
    return path, head


def run_input_head(run_dir: Path) -> tuple[list[str], int]:
    """(表头, 数据行数)。"""

    _, head = _input_lines(run_dir)
    return list(head["headers"]), int(head["rows"])


def run_input_rows(run_dir: Path, indexes: Collection[int]) -> dict[int, dict[str, str]]:
    """按数据行序号（从 0 起）取这几行，读到最大的序号就停；跳过的行不解析。"""

    path, _ = _input_lines(run_dir)
    wanted = set(indexes)
    found: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        handle.readline()
        for index, line in enumerate(itertools.islice(handle, max(wanted, default=-1) + 1)):
            if index in wanted:
                found[index] = json.loads(line)
    return found


# Excel 单元格最多 32767 字，超了文件打不开：截断并标明。
CELL_MAX = 32_000
CELL_CUT = "……（超过 Excel 单元格上限，已截断）"


def excel_cell(value: str) -> str:
    return value if len(value) <= CELL_MAX else value[: CELL_MAX - len(CELL_CUT)] + CELL_CUT


def rows_workbook(headers: list[str], rows: list[list[str]], title: str = "测试数据") -> bytes:
    """表头 + 行生成 Excel（第一行表头），和用户自己上传的 Excel 一个样子。"""

    book = Workbook()
    sheet = active_worksheet(book)
    sheet.title = title
    append_text_row(sheet, headers)
    for row in rows:
        append_text_row(sheet, [excel_cell(str(value or "")) for value in row])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
