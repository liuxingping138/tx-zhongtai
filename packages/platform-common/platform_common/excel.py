"""业务表 Excel 解析与生成。

openpyxl 是纯 CPU 同步库，服务里一律用 *_async 包装放到线程池执行，
否则会把整个服务的事件循环占住。同步版本保留给单元测试直接调用。
"""

from __future__ import annotations

import base64
import zipfile
from collections.abc import Callable, Iterator
from functools import partial
from io import BytesIO
from typing import IO, TYPE_CHECKING, Any

from anyio import CapacityLimiter, to_thread
from defusedxml.ElementTree import iterparse as safe_iterparse
from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

from platform_common.clock import format_beijing
from platform_common.columns import AUDIT_EXPORT_COLUMNS, ColumnSpec, header_to_field
from platform_common.errors import ApiError, ErrorCode

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

# 20MB 压缩包不能代表解压后的大小。这些上限拦住超大表和压缩炸弹，
# 同时仍盖住现有 10 万行导出上限对应的导入规模。
EXCEL_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
EXCEL_MAX_ROWS = 100_000
EXCEL_MAX_COLUMNS = 128
EXCEL_MAX_ZIP_ENTRIES = 64
EXCEL_PARSE_CONCURRENCY = 2
_parse_limiter = CapacityLimiter(EXCEL_PARSE_CONCURRENCY)


def _field_of(columns: tuple[ColumnSpec, ...], header: str) -> str | None:
    raw = (header or "").replace("\n", " ").strip()
    if raw in {"校验说明", "跳过原因"}:
        return "skip_reason"
    return header_to_field(columns, header)


def _reject_oversized_workbook(content: bytes, *, max_uncompressed_bytes: int) -> None:
    """按声明大小和实际解压字节拒绝压缩炸弹。表头撒谎时以读到的字节为准。"""

    if not content.startswith(b"PK"):
        return
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile:
        return
    with archive:
        infos = archive.infolist()
        if len(infos) > EXCEL_MAX_ZIP_ENTRIES:
            raise ApiError("Excel 内部文件过多", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        declared = 0
        for info in infos:
            size = info.file_size
            if size > max_uncompressed_bytes or declared + size > max_uncompressed_bytes:
                raise ApiError("Excel 解压后过大", code=ErrorCode.VALIDATION_ERROR, http_status=422)
            declared += size
        actual = 0
        for info in infos:
            with archive.open(info, "r") as handle:
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    actual += len(block)
                    if actual > max_uncompressed_bytes:
                        raise ApiError("Excel 解压后过大", code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _element_extent(element: Element, tag: str, row_count: int, cell_count: int) -> tuple[int, int, int, int]:
    """返回该元素声明或实际占用的 (行, 列)，以及更新后的行计数、本行单元格计数。0 表示不涉及。"""

    row = col = 0
    if tag == "dimension" and element.get("ref"):
        _, _, max_col, max_row = range_boundaries(element.attrib["ref"])
        col, row = max_col or 0, max_row or 0
    elif tag == "row":
        cell_count = 0
        row_count += 1
        row = max(row_count, int(element.get("r", row_count)))
    elif tag == "c":
        cell_count += 1
        col = cell_count
        if element.get("r"):
            row, coordinate_col = coordinate_to_tuple(element.attrib["r"])
            col = max(col, coordinate_col)
    return row, col, row_count, cell_count


def _check_sheet_coordinates(source: IO[bytes], *, max_rows: int, max_columns: int) -> None:
    """按工作表 XML 的实际坐标限制行列数，不相信声明的 dimension，也挡住稀疏行放大解析量。

    上传文件不可信，用 defusedxml 解析：禁止实体展开和外部实体。
    """

    row_count = cell_count = 0
    for _, element in safe_iterparse(source, events=("end",)):
        tag = element.tag.rsplit("}", 1)[-1]
        row, col, row_count, cell_count = _element_extent(element, tag, row_count, cell_count)
        if row and row > max_rows + 1:
            raise ApiError("Excel 行数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        if col and col > max_columns:
            raise ApiError("Excel 列数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        element.clear()


def iter_workbook_rows(
    content: bytes,
    *,
    max_rows: int = EXCEL_MAX_ROWS,
    max_columns: int = EXCEL_MAX_COLUMNS,
    max_uncompressed_bytes: int = EXCEL_MAX_UNCOMPRESSED_BYTES,
) -> Iterator[tuple[Any, ...]]:
    """校验实际 XML 坐标，避免虚假 dimension 和稀疏行放大解析工作量。"""
    try:
        _reject_oversized_workbook(content, max_uncompressed_bytes=max_uncompressed_bytes)
        with zipfile.ZipFile(BytesIO(content)) as archive:
            for name in archive.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    with archive.open(name) as source:
                        _check_sheet_coordinates(source, max_rows=max_rows, max_columns=max_columns)
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            sheet = book[book.sheetnames[0]]
            # 不相信工作表声明的尺寸；实际坐标已经在 XML 检查中限制。
            sheet.reset_dimensions()
            for count, values in enumerate(sheet.iter_rows(values_only=True), 1):
                if count > max_rows + 1:
                    raise ApiError("Excel 行数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
                if len(values) > max_columns:
                    raise ApiError("Excel 列数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
                yield values
        finally:
            book.close()
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError("无法读取 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc


def parse_sheet(
    content: bytes,
    columns: tuple[ColumnSpec, ...],
    *,
    subject: str = "业务",
    max_rows: int = EXCEL_MAX_ROWS,
    max_columns: int = EXCEL_MAX_COLUMNS,
    max_uncompressed_bytes: int = EXCEL_MAX_UNCOMPRESSED_BYTES,
) -> list[dict[str, str]]:
    rows = iter_workbook_rows(
        content, max_rows=max_rows, max_columns=max_columns, max_uncompressed_bytes=max_uncompressed_bytes
    )
    try:
        mapping: list[str | None] = []
        parse_columns = (*columns, SKIP_REASON_COLUMN)
        for header_row in rows:
            if header_row is None or all(cell is None or str(cell).strip() == "" for cell in header_row):
                continue
            if len(header_row) > max_columns:
                raise ApiError("Excel 列数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
            mapping = [_field_of(columns, str(cell or "")) for cell in header_row]
            if any(mapping):
                break
            raise ApiError(f"Excel 表头与{subject}字段不匹配", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        else:
            raise ApiError("Excel 为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        items: list[dict[str, str]] = []
        for raw in rows:
            if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
                continue
            if len(items) >= max_rows:
                raise ApiError("Excel 行数超过上限", code=ErrorCode.VALIDATION_ERROR, http_status=422)
            item = {spec.field: "" for spec in parse_columns}
            for idx, field in enumerate(mapping):
                if not field or idx >= len(raw):
                    continue
                value = raw[idx]
                item[field] = "" if value is None else str(value).strip()
            items.append(item)
        return items
    finally:
        rows.close()  # type: ignore[attr-defined]


def append_text_row(sheet: Worksheet, values: list[Any] | tuple[Any, ...]) -> None:
    """追加一行，字符串一律按文本写入。

    openpyxl 会把 ``=`` 开头的字符串当成公式保存，打开文件时 Excel 会执行它。
    ``+``、``-``、``@`` 和前导制表符/换行是 Excel 的其它公式入口。导出的值来自用户
    导入和外部爬虫库，这些内容必须保持为文本，再导回来也还是同一个字符串。
    """

    sheet.append([_as_text_cell(sheet, value) for value in values])


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _as_text_cell(sheet: Worksheet, value: Any) -> Any:
    # 公式前缀在 append 时就定成文本。不能 append 后再用 sheet.max_row 回头改类型——
    # max_row 每次扫全表，大表导出会退化成平方复杂度。
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        # 行列号只是占位：append 会按单元格实际所在位置改写。
        cell = Cell(sheet, row=1, column=1, value=value)
        cell.data_type = "s"
        return cell
    return value


def active_worksheet(book: Workbook) -> Worksheet:
    """新建工作簿的活动页一定是普通工作表；openpyxl 的类型上还可能是图表页或 None，这里收窄一次。"""

    sheet = book.active
    if not isinstance(sheet, Worksheet):
        raise TypeError("工作簿没有可写的工作表")
    return sheet


def build_workbook(
    columns: tuple[ColumnSpec, ...],
    rows: list[dict[str, Any]],
    *,
    sheet_name: str,
    include_audit: bool = True,
) -> bytes:
    book = Workbook()
    sheet = active_worksheet(book)
    sheet.title = sheet_name[:31]
    export_cols = (*columns, *AUDIT_EXPORT_COLUMNS) if include_audit else columns
    append_text_row(sheet, [spec.header for spec in export_cols])
    for row in rows:
        values = []
        for spec in export_cols:
            value = row.get(spec.field)
            if spec.field in {"created_at", "updated_at"}:
                values.append(format_beijing(value))
            else:
                values.append("" if value is None else str(value))
        append_text_row(sheet, values)
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
    subject: str = "业务",
    max_rows: int = EXCEL_MAX_ROWS,
    max_columns: int = EXCEL_MAX_COLUMNS,
    max_uncompressed_bytes: int = EXCEL_MAX_UNCOMPRESSED_BYTES,
) -> list[dict[str, str]]:
    """在线程池中解析 Excel，避免阻塞事件循环。同时最多跑两个解析。"""

    async with _parse_limiter:
        return await to_thread.run_sync(
            partial(
                parse_sheet,
                content,
                columns,
                subject=subject,
                max_rows=max_rows,
                max_columns=max_columns,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
        )


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


async def run_excel_parse[ParseResult](func: Callable[..., ParseResult], *args: Any) -> ParseResult:
    """地区解析与标准导入共用并发预算，整个解析/生成流程在线程池中完成。"""
    async with _parse_limiter:
        return await to_thread.run_sync(partial(func, *args))
