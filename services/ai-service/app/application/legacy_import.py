"""把旧 Django 打表系统（difyapi 的 chat_web）的模板和批量历史导进本服务，保留原 ID。

导出目录的结构（在能连旧 MySQL 的机器上导出，再拷到服务器）：
  legacy.json                                  两张旧表：{"templates": [...], "runs": [...]}
  prompt_files/<模板ID>/<模板ID>.xlsx | .txt    旧系统只认这两个名字，「-样例.xlsx」它自己也不读，不导
  batch_runs/<任务ID>/ask_result.xlsx 等         产物文件名与本服务 RUN_FILES 一致

默认已存在的 ID 整条跳过。update=True 时用旧库最新内容覆盖已存在的记录，附件一并替换：
- 模板只覆盖版本号还是 1 的，即导入后没在新系统里保存过；保存过的不动，列在报告里
- 任务 ID 由旧系统生成，撞上的必然是之前导入的，运行中、排队中的除外都覆盖
旧任务没有 Excel 快照，导入后只能查看和下载，不能重跑。
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from platform_common.errors import ApiError
from platform_common.excel import run_excel_parse
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.batch_output import FORMAT_ERROR_PREFIX, read_raw
from app.application.sheets import decode_code_table, sheet_summary
from app.core import storage
from app.domain.models import ACTIVE_STATUSES, RUN_INTERRUPTED, BatchRun, PromptTemplate
from app.domain.templating import split_fields
from app.repositories import batch_runs as run_repo
from app.repositories import billing as billing_repo
from app.repositories import prompts as prompt_repo

IMPORTER = "旧系统迁移"
# 旧系统的 running / stopping 是被杀掉没收尾的任务，在新系统里就是「中断」。
_FINISHED = {"done", "failed", "cancelled", "interrupted"}
_KILO = Decimal(1000)

# 提问内容整段写在 CSV 一格里，默认 128KB 的字段上限不够。
csv.field_size_limit(sys.maxsize)


@dataclass
class ImportReport:
    templates: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _overwrite(existing: Any, fresh: Any, *, keep: tuple[str, ...]) -> None:
    # 只覆盖导入时显式赋过值的列：fresh 上没赋值的（类型、码表、上线版本、来源……）是 None，
    # 搬过去会撞 NOT NULL 让整次导入回滚，release_id 变 None 还会把已上线的模板悄悄下线。
    for attr in inspect(type(fresh)).column_attrs:
        if attr.key not in keep and attr.key in fresh.__dict__:
            setattr(existing, attr.key, getattr(fresh, attr.key))


async def _attach_files(template: PromptTemplate, folder: Path, report: ImportReport) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    excel = folder / f"{template.id}.xlsx"
    if excel.is_file():
        content = excel.read_bytes()
        try:
            template.excel_headers, template.excel_rows = await run_excel_parse(sheet_summary, content)
        except ApiError as exc:
            report.warnings.append(f"模板「{template.title}」的 Excel 没导入：{exc.message}")
        else:
            template.excel_name = f"{template.title}.xlsx"
            files["excel"] = content
    code = folder / f"{template.id}.txt"
    if code.is_file():
        try:
            files["code"] = decode_code_table(code.read_bytes()).encode("utf-8")
        except ApiError as exc:
            report.warnings.append(f"模板「{template.title}」的码表没导入：{exc.message}")
        else:
            template.code_name = f"{template.title}码表.txt"
    return files


async def _import_template(
    session: AsyncSession, row: dict[str, Any], root: Path, report: ImportReport, *, write: bool, update: bool
) -> None:
    prompt_id = row["prompt_id"]
    existing = await prompt_repo.get(session, prompt_id, lock=True)
    if existing is not None and not update:
        report.skipped.append(f"模板 {prompt_id}（{row['title']}）已存在")
        return
    if existing is not None and existing.version > 1:
        report.skipped.append(f"模板「{existing.title}」在新系统里保存过（{existing.updated_by_name}），没有覆盖")
        return
    template = PromptTemplate(
        id=prompt_id,
        title=row["title"],
        content=row["content"],
        output_fields="|".join(split_fields(row.get("output_fields") or "")),
        model_id=row.get("model_id") or "",
        excel_name="",
        excel_rows=0,
        excel_headers=[],
        code_name="",
        version=1,
        created_at=_time(row["created_at"]),
        created_by_id="",
        created_by_name=IMPORTER,
        updated_at=_time(row["updated_at"]),
        updated_by_id="",
        updated_by_name=IMPORTER,
    )
    files = await _attach_files(template, root / "prompt_files" / prompt_id, report)
    if write:
        # 覆盖时旧库没有的附件也要删掉，和旧库保持一致
        storage.remove_tree(storage.prompt_dir(prompt_id))
        for kind, content in files.items():
            storage.write_atomic(storage.prompt_file(prompt_id, kind), content)
    if existing is None:
        prompt_repo.add(session, template)
        report.templates.append(template.title)
    else:
        _overwrite(existing, template, keep=("id", "version", "created_at", "created_by_id", "created_by_name"))
        report.updated.append(f"模板「{template.title}」")


def _usage(raw_csv: Path, row: dict[str, Any]) -> dict[str, int]:
    """token、联网次数、失败条数按原始返回逐行累加；没有原始返回时只能把千 token 总量记在输入一侧。"""

    rows = read_raw(raw_csv).values()
    if not rows:
        return {"input_tokens": int(Decimal(row.get("total_tokens_kilo") or 0) * _KILO)}
    return {
        "input_tokens": sum(item.input_tokens for item in rows),
        "output_tokens": sum(item.output_tokens for item in rows),
        "search_calls": sum(item.search_calls for item in rows),
        "failed_count": sum(1 for item in rows if item.error),
        "format_failed_count": sum(1 for item in rows if item.error.startswith(FORMAT_ERROR_PREFIX)),
    }


def _run_skipped(existing: BatchRun | None, *, update: bool) -> str:
    """已有的任务不导入的原因，空串表示照常导入或覆盖。"""

    if existing is None:
        return ""
    if existing.deleted_at is not None:
        # 在新系统里删过的（只打了删除标记，账单还要算它的钱）：不再导回来，也不能按同一主键再插一行。
        return "已在新系统里删除"
    if not update or existing.status in ACTIVE_STATUSES:
        return "已存在"
    return ""


async def _import_run(
    session: AsyncSession, row: dict[str, Any], root: Path, report: ImportReport, *, write: bool, update: bool
) -> None:
    run_id = row["history_id"]
    existing = await run_repo.get(session, run_id, lock=True, deleted=True)
    if reason := _run_skipped(existing, update=update):
        report.skipped.append(f"任务 {run_id}（{row['prompt_title']}）{reason}")
        return
    source = root / "batch_runs" / run_id
    run = BatchRun(
        id=run_id,
        prompt_id=row["prompt_id"],
        prompt_title=row["prompt_title"],
        prompt_content=row.get("prompt_content") or "",
        output_fields="|".join(split_fields(row.get("output_fields") or "")),
        model_id=row.get("model_id") or "",
        model_name=row.get("model_name") or "",
        thinking=False,
        row_limit=0,
        status=row["status"] if row["status"] in _FINISHED else RUN_INTERRUPTED,
        total_count=int(row.get("total_count") or 0),
        done_count=int(row.get("done_count") or 0),
        failed_count=0,
        format_failed_count=0,
        input_tokens=0,
        output_tokens=0,
        search_calls=0,
        inference_cost=Decimal(row.get("inference_cost") or 0),
        search_cost=Decimal(row.get("search_cost") or 0),
        cancel_requested=bool(int(row.get("cancel_requested") or 0)),
        error_message=row.get("error_msg") or "",
        started_at=_time(row["run_time"]),
        finished_at=_time(row["updated_at"]),
        created_at=_time(row["run_time"]),
        created_by_id="",
        created_by_name=IMPORTER,
    )
    for key, value in _usage(source / storage.RUN_FILES["raw"][0], row).items():
        setattr(run, key, value)
    if write:
        storage.remove_tree(storage.run_dir(run_id))
    missing = []
    for kind, (name, _label) in storage.RUN_FILES.items():
        if (source / name).is_file():
            if not write:
                continue
            target = storage.run_file(run_id, kind)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        elif kind in {"result", "raw"}:
            missing.append(name)
    if missing:
        report.warnings.append(f"任务 {run_id}（{run.prompt_title}）缺少 {'、'.join(missing)}")
    if existing is None:
        run_repo.add(session, run)
        report.runs.append(run_id)
    else:
        _overwrite(existing, run, keep=("id",))
        # 费用换成旧库里最新的累计数：去掉按天的流水，账单按发起那天记这笔整数，不和旧流水叠加。
        await billing_repo.drop_run_costs(session, run_id)
        report.updated.append(f"任务 {run_id}（{run.prompt_title}）")


async def import_legacy(session: AsyncSession, root: Path, *, write: bool = True, update: bool = False) -> ImportReport:
    """调用方负责提交。write=False 时不碰数据卷，只核对。

    文件先落盘再提交：提交失败只留下孤立文件，重跑会覆盖。
    """

    data = json.loads((root / "legacy.json").read_text(encoding="utf-8"))
    report = ImportReport()
    for row in data.get("templates", []):
        await _import_template(session, row, root, report, write=write, update=update)
    for row in data.get("runs", []):
        await _import_run(session, row, root, report, write=write, update=update)
    await session.flush()
    return report
