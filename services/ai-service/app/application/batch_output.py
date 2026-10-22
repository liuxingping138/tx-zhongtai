"""批量产物：原始返回 CSV、运行日志、失败清单、结果 Excel。全部是同步文件操作，调用方放线程池。

结果 Excel = 原 Excel 每行 + 解析出的字段 + 运行信息，一个提问解析出多条就展开成多行；
只保留实际提问完成的行（中途停止时只含已跑部分）。列名口径与旧系统一致。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from platform_common.excel import active_worksheet, append_text_row

from app.domain.templating import extract_fields

RAW_COLUMNS = ["myid", "提问", "model_name", "content", "input_tokens", "output_tokens", "error", "search_count"]
META_COLUMNS = ["model_name", "input_tokens", "output_tokens", "error", "search_count"]
FAILED_COLUMNS = ["myid", "提问", "失败类型", "error", "耗时(秒)"]
# 模型正常回答了但解析不出输出字段。写在 error 列里，原始返回 CSV 不用加列，续跑时也能从文件认出来。
FORMAT_ERROR_PREFIX = "返回格式不对"


@dataclass
class RowResult:
    myid: str
    prompt: str
    text: str
    input_tokens: int
    output_tokens: int
    search_calls: int
    error: str
    elapsed: float
    retryable: bool = False
    attempts: int = 1

    @property
    def format_error(self) -> bool:
        return self.error.startswith(FORMAT_ERROR_PREFIX)

    @property
    def failure_kind(self) -> str:
        if not self.error:
            return ""
        return "格式不对" if self.format_error else "调用失败"

    def raw_row(self, model_name: str) -> list[str]:
        return [
            self.myid,
            self.prompt,
            model_name,
            self.text,
            str(self.input_tokens),
            str(self.output_tokens),
            self.error,
            str(self.search_calls),
        ]


def start_raw(path: Path) -> None:
    """已有文件（续跑）就接着追加，不清空。"""

    if path.is_file():
        return
    # utf-8-sig：Excel 直接双击打开不乱码
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(RAW_COLUMNS)


def read_raw(path: Path) -> dict[str, RowResult]:
    """读回已跑的结果。同一行跑过多次（续跑）以最后一次为准。"""

    if not path.is_file():
        return {}
    results: dict[str, RowResult] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            myid = (row.get("myid") or "").strip()
            if not myid:
                continue
            results[myid] = RowResult(
                myid=myid,
                prompt=row.get("提问") or "",
                text=row.get("content") or "",
                input_tokens=_int(row.get("input_tokens")),
                output_tokens=_int(row.get("output_tokens")),
                search_calls=_int(row.get("search_count")),
                error=row.get("error") or "",
                elapsed=0.0,
            )
    return results


def _int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def append_raw(path: Path, row: list[str]) -> None:
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(row)


def append_log(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def write_failed(path: Path, rows: list[RowResult]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(FAILED_COLUMNS)
        writer.writerows([[row.myid, row.prompt, row.failure_kind, row.error, f"{row.elapsed:.2f}"] for row in rows])


def _unique(name: str, taken: set[str], suffix: str) -> str:
    return name if name not in taken else f"{name}{suffix}"


def result_columns(headers: list[str], fields: list[str]) -> tuple[list[str], list[str], list[str]]:
    """返回 (表头, 解析字段列名, 运行信息列名)。和 Excel 原有列重名时解析字段加「_结果」、运行信息加「_明细」。"""

    taken = {*headers, "myid"}
    parsed = [_unique(name, taken, "_结果") for name in fields]
    taken.update(parsed)
    meta = [_unique(name, taken, "_明细") for name in META_COLUMNS]
    return [*headers, "myid", *parsed, *meta], parsed, meta


# Excel 单元格最多 32767 字，超了文件打不开。流水线任务的正文可能十几万字：结果表里截断并标明，完整内容在原始返回 CSV。
CELL_MAX = 32_000
CELL_CUT = "……（超过 Excel 单元格上限，已截断）"


def _cell(value: str) -> str:
    return value if len(value) <= CELL_MAX else value[: CELL_MAX - len(CELL_CUT)] + CELL_CUT


def build_result(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    results: dict[str, RowResult],
    fields: list[str],
    model_name: str,
) -> None:
    columns, _, _ = result_columns(headers, fields)
    book = Workbook()
    sheet = active_worksheet(book)
    sheet.title = "结果"
    append_text_row(sheet, columns)
    for row in rows:
        result = results.get(row["myid"])
        if result is None:
            continue
        base = [row.get(name, "") for name in headers] + [row["myid"]]
        meta = [model_name, str(result.input_tokens), str(result.output_tokens), result.error, str(result.search_calls)]
        for parsed in extract_fields(result.text, fields):
            append_text_row(sheet, [_cell(value) for value in (*base, *[parsed[name] for name in fields], *meta)])
    temporary = path.with_name(path.name + ".tmp")
    book.save(temporary)
    temporary.replace(path)
