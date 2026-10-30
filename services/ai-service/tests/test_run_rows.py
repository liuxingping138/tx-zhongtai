"""逐行结果预览：任务可能有几十万行，打开详情只读要列的那几行，不为 50 行把整份文件读进内存。"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest

from app.application import run_rows, sheets
from app.application.batch_output import FORMAT_ERROR_PREFIX, RowResult, append_raw, outcomes_path, start_raw
from app.core import storage
from app.domain.models import BatchRun
from app.domain.templating import build_myid
from tests.helpers import run, xlsx

ROWS = 80
OK = '[{"行业":"制造"}]'


def _task(**overrides: Any) -> BatchRun:
    # 每个用例单独一个任务目录：输入副本按目录缓存，共用目录会读到上一个用例的。
    item = run(id=uuid.uuid4().hex, prompt_content="企业：@【名称】", output_fields="行业", **overrides)
    rows = [["名称"], *[[f"企业{index}"] for index in range(ROWS)]]
    storage.write_atomic(storage.run_dir(item.id) / storage.PROMPT_FILES["excel"], xlsx(rows))
    return item


def _answer(item: BatchRun, results: list[tuple[int, str, str]]) -> None:
    path = storage.run_file(item.id, "raw")
    start_raw(path)
    for index, text, error in results:
        append_raw(path, RowResult(build_myid(index), "问" * 1000, text, 10, 5, 0, error, 0.1).raw_row("模型"))


def test_answers_stop_once_the_listed_rows_have_final_results(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _task()
    _answer(item, [(index, OK, "") for index in range(ROWS)])
    read: list[str] = []
    original = run_rows.iter_raw

    def counting(*args: Any, **kwargs: Any) -> Generator[RowResult]:
        for result in original(*args, **kwargs):
            read.append(result.myid)
            yield result

    monkeypatch.setattr(run_rows, "iter_raw", counting)
    data = run_rows.preview(item)
    assert (len(data["items"]), data["total"], data["matched"]) == (run_rows.ROWS_MAX, ROWS, ROWS)
    assert {row["status"] for row in data["items"]} == {"done"}
    assert len(read) == run_rows.ROWS_MAX  # 前 50 行都成功了，后面的结果没读


def test_a_failed_row_shows_its_rerun_result_and_a_lasting_failure_stays() -> None:
    item = _task()
    _answer(item, [(0, "", "限流"), (1, OK, ""), (2, "", "超时"), (0, OK, "")])
    data = run_rows.preview(item, limit=3)
    assert [(row["status"], row["error"]) for row in data["items"]] == [("done", ""), ("done", ""), ("failed", "超时")]


def test_failed_only_counts_failures_anywhere_within_the_run_range() -> None:
    item = _task()
    answers = [(index, OK, "") for index in range(70)]
    answers += [(72, "", "限流"), (75, "我不确定", f"{FORMAT_ERROR_PREFIX}：没有解析出输出字段"), (78, "", "超时")]
    _answer(item, answers)
    first = run_rows.preview(item, failed_only=True, limit=1)
    assert first["matched"] == 3
    assert [(row["row"], row["inputs"], row["status"]) for row in first["items"]] == [
        (73, {"名称": "企业72"}, "failed")
    ]
    item.row_limit = 77  # 只跑前 77 行时，范围外的失败不算
    rows = run_rows.preview(item, failed_only=True)["items"]
    assert [(row["row"], row["status"], row["answer"]) for row in rows] == [
        (73, "failed", ""),
        (76, "format", "我不确定"),
    ]


def test_failed_only_reads_the_outcome_log_not_the_raw_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """原始返回每行带整段提问，大任务有几个 G；只看失败读每行的结果记录。没有记录的老任务照旧读原始返回。"""

    item = _task()
    _answer(item, [(0, "", "限流"), (1, "答非所问", f"{FORMAT_ERROR_PREFIX}：没有解析出输出字段"), (0, OK, "")])

    def forbidden(*_: Any, **__: Any) -> Generator[RowResult]:
        raise AssertionError("不该读原始返回")

    original = run_rows.iter_raw
    monkeypatch.setattr(run_rows, "iter_raw", forbidden)
    rows = run_rows.preview(item, failed_only=True)["items"]
    assert [(row["row"], row["status"], row["answer"]) for row in rows] == [(2, "format", "答非所问")]

    raw = storage.run_file(item.id, "raw")
    outcomes_path(raw).unlink()
    monkeypatch.setattr(run_rows, "iter_raw", original)
    assert [row["row"] for row in run_rows.preview(item, failed_only=True)["items"]] == [2]
    # 已有原始返回却没有记录的任务不补建记录：只记后半截会让前面的失败看不见。
    start_raw(raw)
    assert not outcomes_path(raw).exists()


def test_input_copy_is_parsed_once_and_rebuilt_when_the_snapshot_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = storage.run_dir(_task().id)
    excel = run_dir / storage.PROMPT_FILES["excel"]
    storage.write_atomic(excel, xlsx([["名称", "地区"], ["第一行\n换行", "北京"], ["企业1", "上海"]]))
    assert sheets.run_input_rows(run_dir, [0]) == {0: {"名称": "第一行\n换行", "地区": "北京"}}  # 值里的换行不拆行
    parsed: list[bytes] = []
    original = sheets.read_sheet

    def counting(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
        parsed.append(content)
        return original(content)

    monkeypatch.setattr(sheets, "read_sheet", counting)
    assert sheets.run_input_head(run_dir) == (["名称", "地区"], 2)
    assert sheets.run_input_rows(run_dir, [1]) == {1: {"名称": "企业1", "地区": "上海"}}
    assert parsed == []  # 已有逐行副本，不再解析 Excel
    storage.write_atomic(excel, xlsx([["名称"], ["新数据"]]))
    assert sheets.run_input_rows(run_dir, [0, 5]) == {0: {"名称": "新数据"}}
    assert len(parsed) == 1


def test_pipeline_rows_are_previewed_from_their_json_snapshot() -> None:
    item = run(id=uuid.uuid4().hex, prompt_content="标题：@【政策标题】", output_fields="行业")
    rows = [{"源ID": f"s{index}", "政策标题": f"政策{index}"} for index in range(3)]
    payload = json.dumps({"headers": ["源ID", "政策标题"], "rows": rows}, ensure_ascii=False).encode("utf-8")
    storage.write_atomic(storage.run_dir(item.id) / storage.ROWS_FILE, payload)
    _answer(item, [(1, OK, "")])
    data = run_rows.preview(item)
    assert data["total"] == 3
    assert [(row["inputs"], row["status"]) for row in data["items"]] == [
        ({"政策标题": "政策0"}, "pending"),
        ({"政策标题": "政策1"}, "done"),
        ({"政策标题": "政策2"}, "pending"),
    ]
