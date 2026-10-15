from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook
from platform_common.errors import ApiError

from app.application.batch_output import (
    FORMAT_ERROR_PREFIX,
    RowResult,
    append_log,
    append_raw,
    build_result,
    read_raw,
    result_columns,
    start_raw,
    write_failed,
)
from app.application.sheets import decode_code_table, read_sheet, sheet_summary


def xlsx(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_read_sheet_names_blank_and_duplicate_headers_like_pandas() -> None:
    content = xlsx([[" 名称 ", None, "名称"], ["甲", 1, datetime(2026, 1, 2, 3, 4)], [None, None, None], ["乙"]])
    headers, rows = read_sheet(content)
    assert headers == ["名称", "列2", "名称.1"]
    assert rows == [
        {"名称": "甲", "列2": "1", "名称.1": "2026-01-02 03:04:00"},
        {"名称": "乙", "列2": "", "名称.1": ""},
    ]
    assert read_sheet(content, limit=1)[1] == rows[:1]
    assert sheet_summary(content) == (headers, 2)


def test_sheets_without_data_are_rejected() -> None:
    with pytest.raises(ApiError, match="没有数据行"):
        sheet_summary(xlsx([["名称"]]))
    with pytest.raises(ApiError, match="没有表头"):
        read_sheet(xlsx([]))


def test_code_table_accepts_utf8_bom_and_gbk() -> None:
    assert decode_code_table("\ufeff编码\t名称".encode()) == "编码\t名称"
    assert decode_code_table("编码".encode("gbk")) == "编码"
    with pytest.raises(ApiError):
        decode_code_table(b"\xff\xfe\xfa\xfb\x81")


def test_result_columns_suffix_clashes_like_the_legacy_system() -> None:
    columns, parsed, meta = result_columns(["电话", "error"], ["电话", "行业"])
    assert parsed == ["电话_结果", "行业"]
    assert meta == ["model_name", "input_tokens", "output_tokens", "error_明细", "search_count"]
    assert columns[:3] == ["电话", "error", "myid"]


def _result(myid: str, text: str, error: str = "") -> RowResult:
    return RowResult(myid, f"问 {myid}", text, 10, 5, 1, error, 1.5)


def test_build_result_expands_multiple_entries_and_skips_unfinished_rows(tmp_path: Path) -> None:
    rows = [{"名称": "甲", "myid": "a1"}, {"名称": "=乙", "myid": "a2"}, {"名称": "丙", "myid": "a3"}]
    results = {
        "a1": _result("a1", '[{"行业":"制造"},{"行业":"能源"}]'),
        "a2": _result("a2", "", error="超时"),
    }
    path = tmp_path / "result.xlsx"
    build_result(path, ["名称"], rows, results, ["行业"], "模型A")
    sheet = load_workbook(path).active
    assert sheet is not None
    values = [list(row) for row in sheet.iter_rows(values_only=True)]
    assert values[0] == ["名称", "myid", "行业", "model_name", "input_tokens", "output_tokens", "error", "search_count"]
    assert [row[:3] for row in values[1:]] == [["甲", "a1", "制造"], ["甲", "a1", "能源"], ["=乙", "a2", None]]
    assert values[3][6] == "超时"
    # 「=」开头的用户内容按文本写入，打开文件时不会变成公式
    assert sheet["A4"].data_type == "s"


def test_raw_log_and_failed_files(tmp_path: Path) -> None:
    raw = tmp_path / "temp.csv"
    start_raw(raw)
    append_raw(raw, _result("a1", "答").raw_row("模型A"))
    with raw.open(encoding="utf-8-sig") as handle:
        assert list(csv.reader(handle))[1] == ["a1", "问 a1", "模型A", "答", "10", "5", "", "1"]
    log = tmp_path / "run.log"
    append_log(log, "第一行")
    assert log.read_text(encoding="utf-8") == "第一行\n"
    failed = tmp_path / "failed.csv"
    write_failed(failed, [_result("a2", "", "坏了")])
    with failed.open(encoding="utf-8-sig") as handle:
        assert list(csv.reader(handle)) == [
            ["myid", "提问", "失败类型", "error", "耗时(秒)"],
            ["a2", "问 a2", "调用失败", "坏了", "1.50"],
        ]


def test_raw_file_is_resumed_and_read_back_with_last_attempt_winning(tmp_path: Path) -> None:
    raw = tmp_path / "temp.csv"
    start_raw(raw)
    append_raw(raw, _result("a1", "", "超时").raw_row("模型A"))
    start_raw(raw)
    append_raw(raw, _result("a1", "答").raw_row("模型A"))
    append_raw(raw, _result("a2", "", f"{FORMAT_ERROR_PREFIX}：没有字段").raw_row("模型A"))
    with raw.open("a", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerow(["", "空行号", "", "", "x", "", "", ""])
    results = read_raw(raw)
    assert list(results) == ["a1", "a2"]
    assert (results["a1"].text, results["a1"].error, results["a1"].input_tokens) == ("答", "", 10)
    assert results["a2"].format_error and results["a2"].failure_kind == "格式不对"
    assert results["a1"].failure_kind == ""
    assert read_raw(tmp_path / "missing.csv") == {}
