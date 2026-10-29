"""批量任务和定时任务最多三轮自动重跑、上一批答好的行沿用、上线核对版本号、截停也记用量。"""

from __future__ import annotations

import csv
import json
from collections import Counter
from typing import Any

import pytest
from platform_common.errors import ApiError

from app.application import batch_execute, pipeline_runs, releases, row_asking
from app.application.batch_output import RowResult, append_raw, copy_answers, start_raw
from app.core import storage
from app.core.llm import _StreamState
from app.domain.categories import FULL_ACCESS
from tests.helpers import ACTOR, PROMPT_ID, RUN_ID, FakeSession, run, template
from tests.test_batch import _prepare_execution, _Recorder
from tests.test_releases import READY, _tables

GOOD = [{"text": '[{"行业":"制造"}]'}, {"usage": {"input_tokens": 100, "output_tokens": 10}}]
NETWORK = [{"error": "模型接口响应超时，请稍后重试", "retryable": True}]
BAD_FORMAT = [{"text": "我觉得是制造业"}, {"usage": {"input_tokens": 100, "output_tokens": 10}}]
REJECTED = [{"error": "模型接口返回 HTTP 400：参数不对", "retryable": False}]


def _script(monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[list[dict[str, Any]]]]) -> Counter[str]:
    """按行（提示词里的企业名）给出每次提问的回答，第 N 次问用第 N 个，问超了一直用最后一个。返回每行被问了几次。"""

    asked: Counter[str] = Counter()

    async def stream(request: Any, _client: Any = None) -> Any:
        prompt = json.dumps(request.body, ensure_ascii=False)
        name = next(key for key in answers if f"企业：{key}" in prompt)
        asked[name] += 1
        replies = answers[name]
        for event in replies[min(asked[name], len(replies)) - 1]:
            yield event

    monkeypatch.setattr(row_asking, "stream_responses", stream)
    monkeypatch.setattr(row_asking, "RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(batch_execute, "ROUND_WAITS", (0.0, 0.0))
    return asked


def _log() -> str:
    return storage.run_file(RUN_ID, "log").read_text(encoding="utf-8")


async def test_network_failures_are_asked_again_next_round_and_it_stops_once_all_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run())
    # 乙第一轮当场重发三次都超时（网络抖了一阵子），第二轮就好了。
    asked = _script(monkeypatch, {"甲": [GOOD], "乙": [NETWORK, NETWORK, NETWORK, GOOD], "丙": [GOOD]})
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    assert (final["status"], final["done_count"], final["failed_count"]) == ("done", 3, 0)
    assert asked == {"甲": 1, "乙": 4, "丙": 1}
    assert any(update.get("retry_round") == 2 and update.get("round_rows") == 1 for update in recorder.updates)
    assert "第 2 轮：上一轮 1 条网络失败或格式不对" in _log() and "共跑 2 轮" in _log()
    assert "第 3 轮" not in _log()  # 第二轮全成功就提前结束，不跑满三轮


async def test_bad_format_is_left_to_the_next_round_instead_of_reasked_on_the_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run())
    asked = _script(monkeypatch, {"甲": [GOOD], "乙": [GOOD], "丙": [BAD_FORMAT]})
    await batch_execute.execute(RUN_ID)
    final = recorder.updates[-1]
    # 每轮只问一次，三轮后仍不对就留着失败原因。
    assert asked["丙"] == 3
    assert (final["status"], final["failed_count"], final["format_failed_count"]) == ("done", 1, 1)
    assert "共跑 3 轮" in _log()
    with storage.run_file(RUN_ID, "failed").open(encoding="utf-8-sig") as handle:
        failed = list(csv.reader(handle))
    # 失败清单里的提问是写文件时现拼的，不靠内存里留着。
    assert failed[1][:3] == ["a1000003", "企业：丙", "格式不对"]


async def test_rejected_requests_are_not_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run())
    asked = _script(monkeypatch, {"甲": [GOOD], "乙": [REJECTED], "丙": [GOOD]})
    await batch_execute.execute(RUN_ID)
    assert asked["乙"] == 1 and recorder.updates[-1]["failed_count"] == 1
    assert "第 2 轮" not in _log()


async def test_sample_runs_do_not_go_round_and_reask_bad_format_on_the_spot(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run(source="sample"))
    asked = _script(monkeypatch, {"甲": [GOOD], "乙": [NETWORK], "丙": [BAD_FORMAT]})
    await batch_execute.execute(RUN_ID)
    assert asked == {"甲": 1, "乙": 3, "丙": 2}
    assert "第 2 轮" not in _log()


def _raw(path: Any, rows: list[tuple[str, str, str]]) -> None:
    start_raw(path)
    for myid, text, error in rows:
        append_raw(path, RowResult(myid, f"问 {myid}", text, 50, 5, 0, error, 0.0).raw_row("模型"))


def test_copy_answers_takes_the_last_attempt_and_only_answered_rows(tmp_path: Any) -> None:
    source, target = tmp_path / "old.csv", tmp_path / "new.csv"
    good = '[{"行业":"制造"}]'
    _raw(
        source,
        [
            ("a1000001", good, ""),
            ("a1000002", "", "超时"),
            ("a1000002", good, ""),  # 第二轮答好了
            ("a1000003", good, ""),
            ("a1000003", "", "超时"),  # 最后一次失败了，不能抄
            ("a1000004", "答非所问", ""),  # 解析不出输出字段
        ],
    )
    mapping = {"a1000001": ["a1000003"], "a1000002": ["a1000001", "a1000002"], "a1000003": ["a1000004"]}
    mapping["a1000004"] = ["a1000005"]
    assert copy_answers(source, target, mapping, ["行业"]) == 3
    with target.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["myid"], row["content"], row["提问"]) for row in rows] == [
        ("a1000003", good, "问 a1000001"),
        ("a1000001", good, "问 a1000002"),
        ("a1000002", good, "问 a1000002"),
    ]


def test_reuse_needs_the_same_rows_and_the_same_code_table() -> None:
    previous = run(id="d" * 32, source="pipeline", status="cancelled", release_no=1)
    for folder in (previous.id, RUN_ID):
        storage.remove_tree(storage.run_dir(folder))
    rows = [{"源ID": "1", "正文": "甲"}, {"源ID": "2", "正文": "乙"}]
    pipeline_runs._write_snapshot(previous.id, ["源ID", "正文"], rows, "码表")
    _raw(storage.run_file(previous.id, "raw"), [("a1000001", '[{"行业":"制造"}]', ""), ("a1000002", "", "超时")])
    # 新一批：第 1 行内容没变、第 2 行正文改了，再加一行新的。
    fresh = [{"源ID": "3", "正文": "丙"}, {"源ID": "1", "正文": "甲"}, {"源ID": "2", "正文": "乙改"}]
    pipeline_runs._write_snapshot(RUN_ID, ["源ID", "正文"], fresh, "码表")
    assert pipeline_runs._reuse_answers(previous, RUN_ID, fresh, "码表") == 1
    assert set(batch_execute.read_raw(storage.run_file(RUN_ID, "raw"))) == {"a1000002"}
    assert "沿用上一批" in _log()
    storage.remove_tree(storage.run_dir(RUN_ID))
    pipeline_runs._write_snapshot(RUN_ID, ["源ID", "正文"], fresh, "新码表")
    assert pipeline_runs._reuse_answers(previous, RUN_ID, fresh, "新码表") == 0
    for folder in (previous.id, RUN_ID):
        storage.remove_tree(storage.run_dir(folder))


async def test_publish_refuses_a_draft_changed_after_it_was_reviewed(monkeypatch: pytest.MonkeyPatch) -> None:
    item = template(version=5, **READY)
    _tables(monkeypatch, item, [])
    with pytest.raises(ApiError, match="又被修改过") as caught:
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, version=4)  # type: ignore[arg-type]
    assert caught.value.http_status == 409


def test_truncated_or_filtered_answers_still_report_usage() -> None:
    event = {
        "type": "response.incomplete",
        "response": {
            "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"input_tokens": 5, "output_tokens": 7},
        },
    }
    out = _StreamState().handle(event)
    assert out[0]["error"].startswith("模型未正常完成")
    assert out[1]["usage"]["input_tokens"] == 5 and out[1]["usage"]["output_tokens"] == 7
