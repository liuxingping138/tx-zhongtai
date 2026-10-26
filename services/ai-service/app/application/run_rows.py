"""任务的逐行结果预览：每行用到的输入列、解析出的字段或失败原因。

样本试跑和批量任务详情共用；只看前几十行，完整结果仍是下载的结果 Excel。同步文件操作，调用方放线程池。
"""

from __future__ import annotations

from typing import Any

from app.application.batch_output import read_raw
from app.application.sheets import read_run_input
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


def preview(run: BatchRun, *, failed_only: bool = False, limit: int = ROWS_MAX) -> dict[str, Any]:
    headers, rows = read_run_input(storage.run_dir(run.id))
    total = min(run.row_limit, len(rows)) if run.row_limit else len(rows)
    raw = read_raw(storage.run_file(run.id, "raw"))
    fields = split_fields(run.output_fields)
    columns = [name for name in input_columns(run.prompt_content) if name in headers] or headers[:FALLBACK_COLUMNS]
    items: list[dict[str, Any]] = []
    matched = 0
    for index, row in enumerate(rows[:total]):
        answer = raw.get(build_myid(index))
        status = _status(answer.error if answer else "", bool(answer and answer.format_error), answer is not None)
        if failed_only and status not in ("failed", "format"):
            continue
        matched += 1
        if len(items) >= limit:
            continue
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
