"""样本试跑：草稿 × 模板测试样本的前几条，结果在模板页逐行看；和正式任务互不阻挡。"""

from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import ApiError, NotFoundError

from app.application import batch_runs, prompts, run_compare, sample_runs
from app.application.batch_output import FORMAT_ERROR_PREFIX, RowResult, append_raw, start_raw
from app.application.run_rows import preview
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS
from app.domain.models import RUN_SOURCE_SAMPLE, BatchRun
from app.domain.templating import build_myid
from app.repositories import batch_runs as repo
from app.repositories import prompts as prompt_repo
from tests.helpers import ACTOR, PROMPT_ID, RUN_ID, FakeSession, noop, run, template, xlsx

SAMPLE = xlsx([["名称", "地区"], *[[f"企业{index}", "北京"] for index in range(1, 61)]])


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    added: list[Any] = []
    checked: list[Any] = []

    async def get(*_: Any, **__: Any) -> Any:
        return template(excel_name="样本.xlsx", excel_rows=60, content="草稿：@【名称】")

    async def idle(_session: Any, _prompt_id: str, sources: Any = ()) -> None:
        checked.append(tuple(sources))

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(repo, "active_for_prompt", idle)
    monkeypatch.setattr(repo, "mark_stale_interrupted", noop)

    async def history(_session: Any, _prompt_id: str, *, limit: int) -> tuple[list[Any], int]:
        runs = [row for row in added if isinstance(row, BatchRun)][::-1]
        return runs[:limit], len(runs)

    monkeypatch.setattr(repo, "add", lambda _session, row: added.append(row))
    monkeypatch.setattr(repo, "sample_history", history)
    monkeypatch.setattr(sample_runs, "enqueue_event", noop)
    monkeypatch.setattr(get_settings(), "baidu_api_key", "k")
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), SAMPLE)
    added.append(checked)
    return added


async def test_sample_run_uses_the_saved_draft_and_caps_rows(created: list[Any]) -> None:
    data = await sample_runs.start(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, {"limit": 80, "thinking": True})  # type: ignore[arg-type]
    sources, sample = created
    assert sources == [(RUN_SOURCE_SAMPLE,)]  # 只看有没有样本试跑在跑，不管正式任务
    assert (sample.source, sample.prompt_content, sample.row_limit, sample.total_count) == (
        RUN_SOURCE_SAMPLE,
        "草稿：@【名称】",
        50,
        50,
    )
    assert (sample.input_name, sample.thinking, data["run"]["status"]) == ("样本.xlsx", True, "queued")
    assert (data["run"]["no"], data["compare"], sample.draft_saved_at) == (1, None, template().updated_at)
    assert (storage.run_dir(sample.id) / "source.xlsx").read_bytes() == SAMPLE


async def test_sample_run_needs_a_sample_and_waits_for_the_previous_one(
    created: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def busy(*_: Any, **__: Any) -> Any:
        return run(status="running", done_count=2, total_count=10, source=RUN_SOURCE_SAMPLE)

    monkeypatch.setattr(repo, "active_for_prompt", busy)
    with pytest.raises(ApiError) as conflict:
        await sample_runs.start(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, {})  # type: ignore[arg-type]
    assert conflict.value.http_status == 409 and "2/10" in conflict.value.message

    async def no_sample(*_: Any, **__: Any) -> Any:
        return template(excel_name="")

    monkeypatch.setattr(prompt_repo, "get", no_sample)
    with pytest.raises(ApiError, match="先上传测试样本"):
        await sample_runs.start(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, {})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("draft", "message"),
    [({"content": " "}, "提示词还是空的"), ({"model_id": ""}, "先在模板上选好模型")],
)
async def test_sample_run_needs_a_written_prompt_and_the_templates_own_model(
    created: list[Any], monkeypatch: pytest.MonkeyPatch, draft: dict[str, str], message: str
) -> None:
    """试跑用模板上定好的模型：和上线后跑的是同一个，不拿页面上临时挑的顶替。"""

    async def unfinished(*_: Any, **__: Any) -> Any:
        return template(excel_name="样本.xlsx", excel_rows=60, **draft)

    monkeypatch.setattr(prompt_repo, "get", unfinished)
    with pytest.raises(ApiError, match=message):
        await sample_runs.start(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, {})  # type: ignore[arg-type]
    assert created[1:] == []


def _answers(run_id: str, results: list[tuple[int, str, str]]) -> None:
    path = storage.run_file(run_id, "raw")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    start_raw(path)
    for index, text, error in results:
        item = RowResult(build_myid(index), "问", text, 10, 5, 0, error, 0.1)
        append_raw(path, item.raw_row("模型"))


def test_preview_lists_parsed_fields_failures_and_rows_not_reached() -> None:
    item = run(row_limit=4, total_count=4, prompt_content="企业：@【名称】", output_fields="行业|规模")
    storage.write_atomic(storage.run_dir(RUN_ID) / "source.xlsx", SAMPLE)
    _answers(
        RUN_ID,
        [
            (0, '[{"行业":"制造","规模":"大"},{"行业":"零售","规模":"小"}]', ""),
            (1, "我不确定", f"{FORMAT_ERROR_PREFIX}：回答里没有解析出输出字段（行业、规模）"),
            (2, "", "模型接口返回 HTTP 400：参数错误"),
        ],
    )
    data = preview(item)
    assert (data["columns"], data["fields"], data["total"], data["matched"]) == (["名称"], ["行业", "规模"], 4, 4)
    first, second, third, fourth = data["items"]
    assert first["inputs"] == {"名称": "企业1"} and first["status"] == "done"
    assert first["items"] == [{"行业": "制造", "规模": "大"}, {"行业": "零售", "规模": "小"}]
    assert (second["status"], second["answer"]) == ("format", "我不确定")  # 格式不对时给出模型原话
    assert (third["status"], third["items"], third["answer"]) == ("failed", [], "")
    assert fourth["status"] == "pending"
    failed = preview(item, failed_only=True)
    assert [row["row"] for row in failed["items"]] == [2, 3] and failed["matched"] == 2


def test_preview_without_fields_shows_the_answer_and_truncates_long_cells() -> None:
    item = run(row_limit=1, total_count=1, prompt_content="不引用列", output_fields="")
    storage.write_atomic(storage.run_dir(RUN_ID) / "source.xlsx", SAMPLE)
    _answers(RUN_ID, [(0, "长" * 500, "")])
    row = preview(item)["items"][0]
    assert list(row["inputs"]) == ["名称", "地区"]  # 没引用列时带上前几列，认得出是哪一行
    assert row["answer"].endswith("…") and len(row["answer"]) == 301


def test_template_marks_whether_its_last_sample_ran_the_current_draft() -> None:
    item = template(content="新草稿", output_fields="行业")
    stale = prompts.sample_summary(item, run(prompt_content="旧草稿", source=RUN_SOURCE_SAMPLE))
    fresh = prompts.sample_summary(item, run(prompt_content="新草稿", source=RUN_SOURCE_SAMPLE))
    assert stale is not None and fresh is not None
    assert (stale["current"], fresh["current"]) == (False, True)
    assert prompts.sample_summary(item, None) is None


async def test_formal_task_list_never_shows_sample_runs() -> None:
    assert RUN_SOURCE_SAMPLE not in repo.TASK_SOURCES
    assert batch_runs.to_dict(run(source=RUN_SOURCE_SAMPLE))["source"] == RUN_SOURCE_SAMPLE


async def test_download_only_serves_this_templates_sample_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """下载挂的是模板的导出档，所以只给这个模板自己的样本试跑：拿它去下别的模板或正式任务的结果要 404。"""

    events: list[dict[str, Any]] = []
    sample_id = "d" * 32  # 别的用例会往公用任务目录写日志，这里用自己的目录
    rows = {
        sample_id: run(id=sample_id, source=RUN_SOURCE_SAMPLE),
        "other-prompt": run(id="other-prompt", prompt_id="another", source=RUN_SOURCE_SAMPLE),
        "formal": run(id="formal", source="manual"),
    }

    async def get(_session: Any, run_id: str, **_: Any) -> Any:
        return rows[run_id]

    async def record(*_: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(batch_runs, "require", get)
    monkeypatch.setattr(sample_runs, "enqueue_event", record)
    storage.write_atomic(storage.run_file(sample_id, "result"), b"xlsx")

    path, filename = await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, sample_id, "result")  # type: ignore[arg-type]
    assert (path.read_bytes(), filename) == (b"xlsx", "企业行业-样本试跑结果.xlsx")
    assert events[0]["event_type"] == "ai.prompt.sample_exported"
    assert events[0]["changes"] == {"run_id": sample_id, "file": "result"}

    for run_id in ("other-prompt", "formal"):
        with pytest.raises(NotFoundError):
            await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, run_id, "result")  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, sample_id, "log")  # type: ignore[arg-type]
    assert len(events) == 1


def test_rows_compare_by_row_number() -> None:
    def item(row: int, status: str, items: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {"row": row, "status": status, "items": items or [], "error": "", "answer": ""}

    a, b = [{"行业": "制造"}], [{"行业": "零售"}]
    rows = {
        "items": [item(1, "done", a), item(2, "done", a), item(3, "format"), item(4, "done", b), item(5, "pending")]
    }
    earlier = {
        "items": [item(1, "format"), item(2, "done", a), item(3, "done", a), item(4, "done", a), item(5, "done")]
    }
    counts = run_compare.compare(rows, earlier)
    assert [row["change"] for row in rows["items"]] == ["fixed", "", "broke", "changed", ""]
    assert counts == {"fixed": 1, "broke": 1, "changed": 1, "same": 1}  # 第 5 行这次还没跑到，不算
    assert rows["items"][2]["previous"] == {"status": "done", "items": a, "error": "", "answer": ""}
    assert run_compare.change_of(item(1, "failed"), None) == ""


def test_rewording_prose_is_not_a_change() -> None:
    reason, reworded = "项目" + "是对已有信息系统的运维服务，招标单位是公安局，属于政务部门" * 2, "这是另一种说法" * 8

    def done(scene: str, why: str) -> dict[str, Any]:
        return {"row": 1, "status": "done", "items": [{"三级场景": scene, "打标理由": why}], "error": "", "answer": ""}

    assert run_compare.change_of(done("政务IT运维服务", reworded), done("政务IT运维服务", reason)) == ""
    assert run_compare.change_of(done("", reworded), done("政务IT运维服务", reason)) == "changed"
    assert run_compare.change_of(done("政务IT运维服务", "短理由"), done("政务IT运维服务", "另一个短理由")) == "changed"


def _sample(run_id: str, minute: int, answers: list[tuple[int, str, str]], source: bytes = SAMPLE) -> Any:
    storage.write_atomic(storage.run_dir(run_id) / "source.xlsx", source)
    _answers(run_id, answers)
    created = run(id=run_id, source=RUN_SOURCE_SAMPLE, row_limit=2, total_count=2, output_fields="行业|规模")
    created.created_at = created.created_at.replace(minute=minute)
    return created


def _history(monkeypatch: pytest.MonkeyPatch, runs: list[Any]) -> None:
    async def get(*_: Any, **__: Any) -> Any:
        return template()

    async def history(_session: Any, _prompt_id: str, *, limit: int) -> tuple[list[Any], int]:
        return runs[:limit], len(runs) + 5  # 更早的还有 5 次，不在最近的记录里

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(repo, "sample_history", history)
    monkeypatch.setattr(repo, "mark_stale_interrupted", noop)


async def test_view_compares_with_the_run_before_on_the_same_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, bad = '[{"行业":"制造","规模":"大"}]', f"{FORMAT_ERROR_PREFIX}：没有解析出输出字段"
    newer = _sample("e" * 32, 30, [(0, ok, ""), (1, "说不清", bad)])
    older = _sample("f" * 32, 10, [(0, "说不清", bad), (1, ok, "")])
    _history(monkeypatch, [newer, older])
    data = await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert (data["run"]["id"], data["run"]["no"]) == (newer.id, 7)
    assert [item["no"] for item in data["history"]] == [7, 6]
    compare = data["compare"]
    assert (compare["run"]["no"], compare["same_input"], compare["fixed"], compare["broke"]) == (6, True, 1, 1)
    assert [item["change"] for item in data["rows"]["items"]] == ["fixed", "broke"]

    alone = await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID, compare_id="none")  # type: ignore[arg-type]
    assert alone["compare"] is None and "change" not in alone["rows"]["items"][0]
    first = await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID, run_id=older.id)  # type: ignore[arg-type]
    assert (first["run"]["no"], first["compare"]) == (6, None)  # 最早的一次没有可比的
    with pytest.raises(NotFoundError):
        await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID, run_id="9" * 32)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID, compare_id=newer.id)  # type: ignore[arg-type]


async def test_view_does_not_line_up_rows_of_a_different_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    newer = _sample("e" * 32, 30, [(0, '[{"行业":"制造"}]', "")])
    older = _sample("f" * 32, 10, [(0, '[{"行业":"零售"}]', "")], source=xlsx([["名称"], ["别的企业"]]))
    _history(monkeypatch, [newer, older])
    compare = (await sample_runs.view(FakeSession(), FULL_ACCESS, PROMPT_ID))["compare"]  # type: ignore[arg-type]
    assert (compare["same_input"], "changed" in compare) == (False, False)


async def test_retry_only_takes_this_templates_sample_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    rows = {RUN_ID: run(source=RUN_SOURCE_SAMPLE), "formal": run(id="formal", source="manual")}

    async def get(_session: Any, run_id: str, **_: Any) -> Any:
        return rows[run_id]

    async def retry_run(*args: Any, **kwargs: Any) -> Any:
        calls.append((args[3], kwargs))

    async def view(*_: Any, **kwargs: Any) -> Any:
        return kwargs

    monkeypatch.setattr(batch_runs, "require", get)
    monkeypatch.setattr(batch_runs, "retry_run", retry_run)
    monkeypatch.setattr(sample_runs, "view", view)
    data = await sample_runs.retry(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, RUN_ID)  # type: ignore[arg-type]
    assert data == {"run_id": RUN_ID}
    assert calls == [(RUN_ID, {"event_type": "ai.prompt.sample_retried", "sample": True})]
    with pytest.raises(NotFoundError):
        await sample_runs.retry(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "formal")  # type: ignore[arg-type]


def test_a_sample_is_current_only_while_the_draft_is_unchanged_since_it_ran() -> None:
    """换了码表、重传码表文件也会改保存时间：只比提示词、字段、模型会漏掉，预计费用可能低估几十倍。"""

    from datetime import timedelta

    from app.application.prompts import sample_current

    item = template(content="问", output_fields="行业")
    sample = run(source="sample", prompt_content="问", output_fields="行业", draft_saved_at=item.updated_at)
    assert sample_current(sample, item)
    item.updated_at = item.updated_at + timedelta(minutes=1)  # 只换了码表
    assert not sample_current(sample, item)
    legacy = run(source="sample", prompt_content="问", output_fields="行业", draft_saved_at=None)
    assert sample_current(legacy, item)  # 早期试跑没记保存时间，退回按内容比
