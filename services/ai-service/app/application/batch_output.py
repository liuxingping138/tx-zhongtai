"""批量产物：原始返回 CSV、运行日志、失败清单、结果 Excel。全部是同步文件操作，调用方放线程池。

结果 Excel = 原 Excel 每行 + 解析出的字段 + 运行信息，一个提问解析出多条就展开成多行；
只保留实际提问完成的行（中途停止时只含已跑部分）。列名口径与旧系统一致。
"""

from __future__ import annotations

import csv
import io
import json
import sys
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_common.xlsx_writer import write_text_xlsx

from app.application.sheets import excel_cell
from app.domain.templating import extract_fields, parse_fields

# 「提问」列是整段提示词：政策全文加六级码表能到十几万字，csv 默认 131072 字的单格上限会让整份结果读不回来，钱白花。
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))  # Windows 的 C long 是 32 位，sys.maxsize 会溢出

# cached_tokens（命中上下文缓存的输入 token）加在最后：这一列上线前开始的任务，原始返回只有前 8 列，
# 续跑时按文件自己的表头接着写（raw_columns），读的时候缺这一列算 0。
LEGACY_RAW_COLUMNS = ["myid", "提问", "model_name", "content", "input_tokens", "output_tokens", "error", "search_count"]
RAW_COLUMNS = [*LEGACY_RAW_COLUMNS, "cached_tokens"]
META_COLUMNS = ["model_name", "input_tokens", "output_tokens", "error", "search_count"]
FAILED_COLUMNS = ["myid", "提问", "失败类型", "error", "耗时(秒)"]
# 模型正常回答了但解析不出输出字段。写在 error 列里，原始返回 CSV 不用加列，续跑时也能从文件认出来。
FORMAT_ERROR_PREFIX = "返回格式不对"


def sanitize_csv_cell(value: Any) -> str:
    """防止 CSV 公式注入 (DDE)，开头的公式触发字符追加单引号转义。"""
    text = str(value) if value is not None else ""
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
        return "'" + text
    return text


def sanitize_csv_row(row: Sequence[Any]) -> list[str]:
    return [sanitize_csv_cell(val) for val in row]


class _BoundedBinaryReader(io.RawIOBase):
    def __init__(self, handle: io.BufferedReader, limit: int) -> None:
        self._handle = handle
        self._left = limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        if self._left <= 0:
            return 0
        chunk = self._handle.read(min(len(buffer), self._left))
        if not chunk:
            return 0
        self._left -= len(chunk)
        buffer[: len(chunk)] = chunk
        return len(chunk)


def iter_sanitized_csv(path: Path, max_bytes: int | None = None) -> Iterator[bytes]:
    """流式导出 CSV 并在导出时做公式转义：盘上 temp.csv 保持原文供机器解析，下载时再防 DDE 注入。"""

    limit = path.stat().st_size if max_bytes is None else max_bytes
    with path.open("rb") as raw_handle:
        bom = raw_handle.read(min(3, limit)) == b"\xef\xbb\xbf"
        raw_handle.seek(0)
        bounded = io.BufferedReader(_BoundedBinaryReader(raw_handle, limit))
        with io.TextIOWrapper(bounded, encoding="utf-8-sig", newline="") as handle:
            first = True
            for row in csv.reader(handle):
                buf = io.StringIO()
                csv.writer(buf).writerow(sanitize_csv_row(row))
                chunk = buf.getvalue().encode("utf-8")
                yield (b"\xef\xbb\xbf" + chunk) if (first and bom) else chunk
                first = False


# 每写一行原始返回，同时在这里记一行「这一行成没成、错在哪」，不带提问原文。详情「只看失败」读它：
# 原始返回每行带着整段提问，几十万行的任务有几个 G，跑着时每 10 秒整份扫一遍会超时。
OUTCOMES_SUFFIX = ".outcomes.jsonl"
# 失败行的回答只留开头，页面也只显示前 300 字。
OUTCOME_TEXT_MAX = 400


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
    cached_tokens: int = 0
    # 这一行在原始返回 CSV 里的字节位置（结果记录里记的）：详情预览按它直接取，不用从头扫几个 G。-1 表示不知道。
    offset: int = -1

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
            str(self.cached_tokens),
        ]


def answered(result: RowResult, fields: list[str]) -> bool:
    """这一行算答好了：没报错，要解析输出字段的还得解析得出来。"""

    return not result.error and (not fields or parse_fields(result.text, fields) is not None)


def start_raw(path: Path) -> None:
    """已有文件（续跑）就接着追加，不清空。

    结果记录和原始返回同时新建：已有原始返回、却没有结果记录的（这个功能上线前开始的任务）一直不建，
    免得只记了后半截、看起来没有失败。
    """

    if path.is_file():
        return
    # utf-8-sig：Excel 直接双击打开不乱码
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(RAW_COLUMNS)
    outcomes_path(path).write_text("", encoding="utf-8")


def raw_columns(path: Path) -> list[str]:
    """已有原始返回的列：缓存列上线前开始的任务是旧的 8 列，续跑、抄答案时照它写，不然新行多一格、整份读错位。"""

    if not path.is_file():
        return RAW_COLUMNS
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), None)
    return LEGACY_RAW_COLUMNS if header == LEGACY_RAW_COLUMNS else RAW_COLUMNS


def _fit(row: list[str], columns: list[str]) -> list[str]:
    """按目标文件的列裁掉新加的列（旧文件不认 cached_tokens）。"""

    return row[: len(columns)]


def outcomes_path(raw: Path) -> Path:
    return raw.with_suffix(OUTCOMES_SUFFIX)


def _append_outcome(raw: Path, row: list[str], offset: int) -> None:
    target = outcomes_path(raw)
    if not target.is_file():
        return
    record = dict(zip(RAW_COLUMNS, row, strict=False))
    line: dict[str, str | int] = {"myid": record["myid"], "error": record["error"], "at": offset}
    if record["error"]:
        line["text"] = record["content"][:OUTCOME_TEXT_MAX]
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def iter_outcomes(raw: Path) -> Generator[RowResult] | None:
    """按写入顺序读结果记录（不带提问、只有失败行带回答开头）。没有记录文件时返回 None，调用方改读原始返回。"""

    target = outcomes_path(raw)
    if not target.is_file():
        return None
    return _read_outcomes(target)


def _read_outcomes(target: Path) -> Generator[RowResult]:
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:  # 执行进程正写到一半的最后一行，下次再读
                continue
            yield RowResult(
                myid=record["myid"],
                prompt="",
                text=record.get("text", ""),
                input_tokens=0,
                output_tokens=0,
                search_calls=0,
                error=record["error"],
                elapsed=0.0,
                offset=int(record.get("at", -1)),
            )


def raw_at(path: Path, offset: int) -> RowResult | None:
    """按结果记录里的字节位置取原始返回的一行（不带提问）。位置不对（文件被重写过）返回 None，调用方改为顺序读。"""

    with path.open("rb") as binary:
        binary.seek(offset)
        with io.TextIOWrapper(binary, encoding="utf-8", newline="") as handle:
            row = next(csv.reader(handle), None)
    if row is None or len(row) not in (len(RAW_COLUMNS), len(LEGACY_RAW_COLUMNS)):
        return None
    record = dict(zip(RAW_COLUMNS, row, strict=False))
    return RowResult(
        myid=record["myid"].strip(),
        prompt="",
        text=record["content"],
        input_tokens=_int(record["input_tokens"]),
        output_tokens=_int(record["output_tokens"]),
        search_calls=_int(record["search_count"]),
        error=record["error"],
        elapsed=0.0,
        cached_tokens=_int(record.get("cached_tokens")),
    )


def read_raw(path: Path) -> dict[str, RowResult]:
    """读回已跑的结果，不带提问原文。同一行跑过多次（续跑、多轮）以最后一次为准。"""

    return {result.myid: result for result in iter_raw(path)}


def iter_raw(path: Path, *, with_prompt: bool = False) -> Generator[RowResult]:
    """按写入顺序逐条读。with_prompt=False 不留提问原文：每行的提问带着整段正文甚至码表，几十万行整份留下能占几个 G。"""

    if not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            myid = (row.get("myid") or "").strip()
            if not myid:
                continue
            yield RowResult(
                myid=myid,
                prompt=(row.get("提问") or "") if with_prompt else "",
                text=row.get("content") or "",
                input_tokens=_int(row.get("input_tokens")),
                output_tokens=_int(row.get("output_tokens")),
                search_calls=_int(row.get("search_count")),
                error=row.get("error") or "",
                elapsed=0.0,
                cached_tokens=_int(row.get("cached_tokens")),
            )


def _int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def append_raw(path: Path, row: list[str]) -> None:
    """同一任务同时只能有一个写入方（batch_execute 用 Job.write_lock 排队），记下的字节位置才准。"""

    raw_row = _fit(row, raw_columns(path))
    offset = path.stat().st_size if path.is_file() else 0
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(raw_row)
    _append_outcome(path, raw_row, offset)


def append_log(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def write_failed(path: Path, rows: Iterable[RowResult], prompt_of: Callable[[str], str]) -> None:
    """失败清单。提问原文逐行现拼现写（prompt_of），不在内存里攒着。"""

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(FAILED_COLUMNS)
        for row in rows:
            safe_failed_row = sanitize_csv_row(
                [row.myid, prompt_of(row.myid), row.failure_kind, row.error, f"{row.elapsed:.2f}"]
            )
            writer.writerow(safe_failed_row)


def copy_answers(source: Path, target: Path, mapping: dict[str, list[str]], fields: list[str]) -> int:
    """把另一个任务里已经答好的行抄进新任务的原始返回（换成新行号），worker 续跑时就不再问它们，也不再计费。

    mapping：源行号 -> 新任务里内容完全相同的行号（可能有几行）。源文件里同一行有几条（续跑、多轮）时以最后一条为准，
    只抄答好的。先不带提问读一遍定下抄哪几条，再逐行流式抄：原始返回每行带着整段提问，不能整份读进内存。返回抄了几行。
    """

    final: dict[str, int] = {}
    good: set[int] = set()
    for index, result in enumerate(iter_raw(source)):
        if result.myid not in mapping:
            continue
        final[result.myid] = index
        if answered(result, fields):
            good.add(index)
    chosen = {index for index in final.values() if index in good}
    if not chosen:
        return 0
    start_raw(target)
    columns = raw_columns(target)
    copied = 0
    with (
        source.open(encoding="utf-8-sig", newline="") as reader,
        target.open("a", newline="", encoding="utf-8-sig") as writer_handle,
    ):
        writer = csv.writer(writer_handle)
        index = -1
        for row in csv.DictReader(reader):
            myid = (row.get("myid") or "").strip()
            if not myid:
                continue
            index += 1
            if index not in chosen:
                continue
            for new_id in mapping[myid]:
                values = [new_id if column == "myid" else row.get(column) or "" for column in columns]
                writer_handle.flush()
                offset = target.stat().st_size
                writer.writerow(values)
                _append_outcome(target, values, offset)
                copied += 1
    return copied


def _unique(name: str, taken: set[str], suffix: str) -> str:
    return name if name not in taken else f"{name}{suffix}"


def result_columns(headers: list[str], fields: list[str]) -> tuple[list[str], list[str], list[str]]:
    """返回 (表头, 解析字段列名, 运行信息列名)。和 Excel 原有列重名时解析字段加「_结果」、运行信息加「_明细」。"""

    taken = {*headers, "myid"}
    parsed = [_unique(name, taken, "_结果") for name in fields]
    taken.update(parsed)
    meta = [_unique(name, taken, "_明细") for name in META_COLUMNS]
    return [*headers, "myid", *parsed, *meta], parsed, meta


# 流水线任务的正文可能十几万字：结果表里截断并标明（见 sheets.excel_cell），完整内容在原始返回 CSV。
_cell = excel_cell


def build_result(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    results: dict[str, RowResult],
    fields: list[str],
    model_name: str,
) -> None:
    columns, _, _ = result_columns(headers, fields)

    # 逐行流式写、只含文本的 xlsx：openpyxl 逐格建对象，10 万行要吃几个 G 内存。
    def lines() -> Iterator[list[str]]:
        yield list(columns)
        for row in rows:
            result = results.get(row["myid"])
            if result is None:
                continue
            base = [row.get(name, "") for name in headers] + [row["myid"]]
            tokens = (str(result.input_tokens), str(result.output_tokens))
            meta = [model_name, *tokens, result.error, str(result.search_calls)]
            for parsed in extract_fields(result.text, fields):
                yield [_cell(value) for value in (*base, *[parsed[name] for name in fields], *meta)]

    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(write_text_xlsx("结果", lines(), column_count=len(columns)))
    temporary.replace(path)
