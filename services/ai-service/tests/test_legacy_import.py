from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from app.application import legacy_import as service
from app.application.batch_output import RAW_COLUMNS
from app.core import storage
from app.domain.models import BatchRun, PromptTemplate
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as prompt_repo
from tests.helpers import FakeSession, xlsx

PROMPT_ID = "1" * 32
RUN_ID = "2" * 32
STOPPED_ID = "3" * 32


def _bundle(root: Path) -> Path:
    templates = [
        {
            "prompt_id": PROMPT_ID,
            "title": "政策解读",
            "content": "解读 @【标题】",
            "output_fields": " 行业 | 场景 ",
            "model_id": "deepseek-v4-flash-nw",
            "created_at": "2026-09-15T07:00:00.000000+00:00",
            "updated_at": "2026-10-21T03:26:27.713581+00:00",
        }
    ]
    run = {
        "prompt_id": PROMPT_ID,
        "prompt_title": "政策解读",
        "prompt_content": "解读 @【标题】",
        "output_fields": "行业|场景",
        "model_id": "deepseek-v4-flash-nw",
        "model_name": "deepseek-v4-flash（不联网）",
        "total_count": 3,
        "done_count": 3,
        "total_tokens_kilo": "1.500",
        "inference_cost": "0.766650",
        "search_cost": "0.000000",
        "cancel_requested": 0,
        "error_msg": "",
        "run_time": "2026-10-15T06:31:19.106770+00:00",
        "updated_at": "2026-10-15T06:40:00.000000+00:00",
    }
    runs = [
        {**run, "history_id": RUN_ID, "status": "done"},
        {**run, "history_id": STOPPED_ID, "status": "running", "total_tokens_kilo": "2.000"},
    ]
    (root / "legacy.json").write_text(json.dumps({"templates": templates, "runs": runs}), encoding="utf-8")
    files = root / "prompt_files" / PROMPT_ID
    files.mkdir(parents=True)
    (files / f"{PROMPT_ID}.xlsx").write_bytes(xlsx([["标题"], ["甲"], ["乙"]]))
    (files / f"{PROMPT_ID}.txt").write_bytes("制造业\n".encode("gbk"))
    (files / f"{PROMPT_ID}-样例.xlsx").write_bytes(b"ignored")
    outputs = root / "batch_runs" / RUN_ID
    outputs.mkdir(parents=True)
    (outputs / "ask_result.xlsx").write_bytes(b"result")
    with (outputs / "temp.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(RAW_COLUMNS)
        writer.writerow(["a1000001", "问", "m", "答", "100", "20", "", "1"])
        writer.writerow(["a1000002", "问", "m", "答", "300", "80", "返回格式不对：没有字段", "0"])
        writer.writerow(["a1000003", "问", "m", "", "0", "0", "HTTP 500", "0"])
    return root


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    existing: dict[str, Any] = {}

    async def get(_session: object, item_id: str, *, lock: bool = False) -> object | None:
        return existing.get(item_id)

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(run_repo, "get", get)
    return existing


def _added(session: FakeSession, kind: type) -> list[Any]:
    return [item for item in session.added if isinstance(item, kind)]


async def test_imports_templates_runs_and_files(tmp_path: Path, stored: dict[str, Any]) -> None:
    session = FakeSession()
    report = await service.import_legacy(session, _bundle(tmp_path))  # type: ignore[arg-type]

    [template] = _added(session, PromptTemplate)
    assert (template.id, template.output_fields, template.excel_rows, template.excel_headers) == (
        PROMPT_ID,
        "行业|场景",
        2,
        ["标题"],
    )
    assert (template.excel_name, template.code_name, template.created_by_name) == (
        "政策解读.xlsx",
        "政策解读码表.txt",
        "旧系统迁移",
    )
    assert storage.prompt_file(PROMPT_ID, "code").read_text(encoding="utf-8") == "制造业\n"

    done, stopped = _added(session, BatchRun)
    assert (done.input_tokens, done.output_tokens, done.search_calls) == (400, 100, 1)
    assert (done.failed_count, done.format_failed_count, str(done.inference_cost)) == (2, 1, "0.766650")
    assert storage.run_file(RUN_ID, "result").read_bytes() == b"result"
    # 没收尾的旧任务记为中断；没有原始返回时千 token 总量记在输入一侧
    assert (stopped.status, stopped.input_tokens) == ("interrupted", 2000)
    assert report.warnings == [f"任务 {STOPPED_ID}（政策解读）缺少 ask_result.xlsx、temp.csv"]


async def test_existing_ids_are_skipped(tmp_path: Path, stored: dict[str, Any]) -> None:
    stored.update({PROMPT_ID: object(), RUN_ID: object()})
    session = FakeSession()
    report = await service.import_legacy(session, _bundle(tmp_path))  # type: ignore[arg-type]

    assert [item.id for item in session.added] == [STOPPED_ID]
    assert len(report.skipped) == 2


async def test_dry_run_leaves_data_volume_untouched(tmp_path: Path, stored: dict[str, Any]) -> None:
    bundle = _bundle(tmp_path)
    storage.remove_tree(storage.prompt_dir(PROMPT_ID))
    storage.remove_tree(storage.run_dir(RUN_ID))
    report = await service.import_legacy(FakeSession(), bundle, write=False)  # type: ignore[arg-type]

    assert report.templates == ["政策解读"]
    assert not storage.prompt_dir(PROMPT_ID).exists()
    assert not storage.run_dir(RUN_ID).exists()


async def test_template_with_unreadable_excel_imports_without_it(tmp_path: Path, stored: dict[str, Any]) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "prompt_files" / PROMPT_ID / f"{PROMPT_ID}.xlsx").write_bytes(xlsx([["标题"]]))
    session = FakeSession()
    report = await service.import_legacy(session, bundle)  # type: ignore[arg-type]

    [template] = _added(session, PromptTemplate)
    assert (template.excel_name, template.excel_rows) == ("", 0)
    assert report.warnings[0] == "模板「政策解读」的 Excel 没导入：Excel 没有数据行"


async def test_update_overwrites_untouched_records_and_replaces_files(tmp_path: Path, stored: dict[str, Any]) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "prompt_files" / PROMPT_ID / f"{PROMPT_ID}.txt").unlink()
    old_template = PromptTemplate(
        id=PROMPT_ID, title="旧标题", version=1, code_name="旧码表.txt", created_by_name="导入"
    )
    old_run = BatchRun(id=RUN_ID, status="interrupted", done_count=1)
    stored.update({PROMPT_ID: old_template, RUN_ID: old_run})
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), b"old")
    session = FakeSession()
    report = await service.import_legacy(session, bundle, update=True)  # type: ignore[arg-type]

    assert (old_template.title, old_template.excel_rows, old_template.code_name) == ("政策解读", 2, "")
    assert (old_template.version, old_template.created_by_name, old_template.updated_by_id) == (1, "导入", "")
    # 覆盖时每个非空列都要有值：列默认值只在 INSERT 时生效
    assert old_run.created_by_id == ""
    # 旧库已经没有码表，覆盖后数据卷里也不留
    assert not storage.prompt_file(PROMPT_ID, "code").exists()
    assert (old_run.status, old_run.done_count, old_run.input_tokens) == ("done", 3, 400)
    assert [item.id for item in session.added] == [STOPPED_ID]
    assert report.updated == ["模板「政策解读」", f"任务 {RUN_ID}（政策解读）"]


async def test_update_keeps_templates_edited_in_new_system_and_active_runs(
    tmp_path: Path, stored: dict[str, Any]
) -> None:
    edited = PromptTemplate(id=PROMPT_ID, title="新系统改过", version=3, updated_by_name="张三")
    running = BatchRun(id=RUN_ID, status="running")
    stored.update({PROMPT_ID: edited, RUN_ID: running})
    report = await service.import_legacy(FakeSession(), _bundle(tmp_path), update=True)  # type: ignore[arg-type]

    assert (edited.title, running.status) == ("新系统改过", "running")
    assert report.skipped == [
        "模板「新系统改过」在新系统里保存过（张三），没有覆盖",
        f"任务 {RUN_ID}（政策解读）已存在",
    ]
