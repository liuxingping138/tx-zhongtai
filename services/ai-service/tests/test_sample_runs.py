"""样本试跑：草稿 × 模板测试样本的前几条，结果在模板页逐行看；和正式任务互不阻挡。"""

from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import ApiError, NotFoundError

from app.application import batch_runs, prompts, sample_runs
from app.application.batch_output import FORMAT_ERROR_PREFIX, RowResult, append_raw, start_raw
from app.application.run_rows import preview
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS
from app.domain.models import RUN_SOURCE_SAMPLE
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
    monkeypatch.setattr(repo, "add", lambda _session, row: added.append(row))
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

    content, filename = await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, sample_id, "result")  # type: ignore[arg-type]
    assert (content, filename) == (b"xlsx", "企业行业-样本试跑结果.xlsx")
    assert events[0]["event_type"] == "ai.prompt.sample_exported"
    assert events[0]["changes"] == {"run_id": sample_id, "file": "result"}

    for run_id in ("other-prompt", "formal"):
        with pytest.raises(NotFoundError):
            await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, run_id, "result")  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await sample_runs.download(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, sample_id, "log")  # type: ignore[arg-type]
    assert len(events) == 1
