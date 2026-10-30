"""任务的逐行结果预览：每行用到的输入列、解析出的字段或失败原因。

样本试跑和批量任务详情共用；只看前几十行，完整结果仍是下载的结果 Excel。同步文件操作，调用方放线程池。
任务可能有几十万行：输入按行副本只读到要列的那几行，原始返回不留提问原文，不为 50 行把整份文件读进内存。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from app.application.batch_output import RowResult, iter_outcomes, iter_raw, raw_at
from app.application.row_asking import needs_retry
from app.application.sheets import run_input_head, run_input_rows
from app.core import storage
from app.domain.models import BatchRun
from app.domain.releases import input_columns
from app.domain.templating import build_myid, parse_fields, split_fields

ROWS_MAX = 50
CELL_MAX = 300
# 提示词没引用任何列时（如只问码表），预览至少带上前几列，好认出是哪一行。
FALLBACK_COLUMNS = 3


def _short(value: str) -> str:
    return value if len(value) <= CELL_MAX else value[:CELL_MAX] + "…"


def _status(error: str, format_error: bool, answered: bool) -> str:
    if not answered:
        return "pending"
    if format_error:
        return "format"
    return "failed" if error else "done"


def _first_answers(raw: Path, count: int, fields: list[str]) -> dict[int, RowResult]:
    """前 count 行各自最后一次的结果。

    有结果记录时按它定下每行的最终结果：失败行用记录里的说明，成功行按记下的字节位置直接从原始返回取那一行。
    原来顺序读原始返回，前几十行里只要有一行最终失败（或第 2 轮才答好、记在文件末尾），就要扫完整份，
    十万行带码表的任务十几 G，打开详情就超时。没有记录（功能上线前的任务）或位置对不上时才顺序读。
    """

    wanted = {build_myid(index): index for index in range(count)}
    if not wanted:
        return {}
    outcomes = iter_outcomes(raw)
    if outcomes is None:
        return _scan_answers(raw, wanted, fields)
    final: dict[str, RowResult] = {}
    for result in outcomes:
        if result.myid in wanted:
            final[result.myid] = result
    found: dict[int, RowResult] = {}
    unknown: dict[str, int] = {}
    for myid, result in final.items():
        located = result if result.error or result.offset < 0 else raw_at(raw, result.offset)
        if result.error or (located is not None and located.myid == myid):
            found[wanted[myid]] = located or result
        else:
            unknown[myid] = wanted[myid]
    if unknown:
        found.update(_scan_answers(raw, unknown, fields))
    return found


def _scan_answers(raw: Path, wanted: dict[str, int], fields: list[str]) -> dict[int, RowResult]:
    """顺序读原始返回。重跑只重问失败的行（needs_retry），成功的那次就是最终结果：这几行都成功了就不再往下读。"""

    unsettled = set(wanted)
    found: dict[int, RowResult] = {}
    with contextlib.closing(iter_raw(raw, with_prompt=False)) as results:
        for result in results:
            index = wanted.get(result.myid)
            if index is None:
                continue
            found[index] = result
            if not needs_retry(result, fields):
                unsettled.discard(result.myid)
                if not unsettled:
                    break
    return found


def _failures(raw: Path, total: int) -> dict[int, RowResult]:
    """前 total 行里最后一次失败（含格式不对）的行，按行号排。只看失败时才用：失败的行可能在任何位置，要读完整份。

    读每行的结果记录（几十万行也只有几 MB）；记录功能上线前开始的任务没有它，才整份读原始返回。
    """

    latest: dict[str, RowResult | None] = {}
    results = iter_outcomes(raw)
    for result in iter_raw(raw, with_prompt=False) if results is None else results:
        latest[result.myid] = result if result.error else None
    found: dict[int, RowResult] = {}
    for index in range(total):
        failed = latest.get(build_myid(index))
        if failed is not None:
            found[index] = failed
    return found


def preview(run: BatchRun, *, failed_only: bool = False, limit: int = ROWS_MAX) -> dict[str, Any]:
    run_dir, raw = storage.run_dir(run.id), storage.run_file(run.id, "raw")
    headers, count = run_input_head(run_dir)
    total = min(run.row_limit, count) if run.row_limit else count
    fields = split_fields(run.output_fields)
    columns = [name for name in input_columns(run.prompt_content) if name in headers] or headers[:FALLBACK_COLUMNS]
    if failed_only:
        failures = _failures(raw, total)
        matched, indexes, answers = len(failures), list(failures)[:limit], failures
    else:
        matched, indexes = total, list(range(min(total, limit)))
        answers = _first_answers(raw, len(indexes), fields)
    inputs = run_input_rows(run_dir, indexes)
    items: list[dict[str, Any]] = []
    for index in indexes:
        row, answer = inputs.get(index, {}), answers.get(index)
        status = _status(answer.error if answer else "", bool(answer and answer.format_error), answer is not None)
        parsed = parse_fields(answer.text, fields) if answer and status == "done" and fields else None
        items.append(
            {
                "row": index + 1,
                "inputs": {name: _short(str(row.get(name) or "")) for name in columns},
                "status": status,
                "error": answer.error if answer else "",
                "items": [{key: _short(value) for key, value in entry.items()} for entry in parsed or []],
                # 没设输出字段、或者格式不对时，给出模型的原话，方便看它到底回了什么。
                "answer": _short(answer.text) if answer and (not fields or status == "format") else "",
            }
        )
    return {"columns": columns, "fields": fields, "items": items, "matched": matched, "total": total}
