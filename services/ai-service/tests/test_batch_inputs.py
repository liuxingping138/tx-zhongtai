"""批量任务：只跑上线版本，本次数据单独上传、按上线版本校验列，输入和码表冻结进任务。"""

from typing import Any

import pytest
from platform_common.errors import ApiError, PermissionDeniedError

from app.application import batch_runs, releases
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS, CategoryAccess
from app.domain.models import TemplateRelease
from app.repositories import batch_runs as repo
from app.repositories import prompts as prompt_repo
from app.repositories import releases as release_repo
from tests.helpers import ACTOR, PROMPT_ID, RELEASE_ID, FakeSession, noop, release, run, template, xlsx


def _online(monkeypatch: pytest.MonkeyPatch, item: TemplateRelease | None, **draft: Any) -> list[Any]:
    """模板草稿已经改成引用 @【草稿列】，上线版本仍引用 @【名称】：批量任务必须按上线版本。"""

    added: list[Any] = []

    async def get(*_: Any, **__: Any) -> Any:
        values = {"content": "草稿：@【草稿列】", "release_id": RELEASE_ID if item else None, **draft}
        return template(**values)

    async def by_ids(_session: Any, ids: list[str]) -> dict[str, TemplateRelease]:
        return {item.id: item} if item and item.id in ids else {}

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(release_repo, "by_ids", by_ids)
    monkeypatch.setattr(repo, "active_for_prompt", noop)
    monkeypatch.setattr(repo, "mark_stale_interrupted", noop)
    monkeypatch.setattr(repo, "add", lambda _session, row: added.append(row))
    monkeypatch.setattr(batch_runs, "enqueue_event", noop)
    monkeypatch.setattr(get_settings(), "baidu_api_key", "test")
    return added


async def test_start_runs_the_release_with_its_own_file(monkeypatch: pytest.MonkeyPatch) -> None:
    added = _online(monkeypatch, release(), excel_name="样本.xlsx")
    sample = xlsx([["草稿列"], ["样本"]])
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), sample)
    upload = (r"C:\fakepath\正式.xlsx", xlsx([["名称"], ["甲"], ["乙"], ["丙"]]))
    data = await batch_runs.start_run(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        FULL_ACCESS,
        {"prompt_id": PROMPT_ID, "limit": 2},
        upload=upload,
    )
    created = added[0]
    assert (created.prompt_content, created.release_no, created.source) == ("企业：@【名称】", 3, "manual")
    assert (data["input_name"], data["total_count"], data["row_limit"], data["run_mode"]) == ("正式.xlsx", 2, 2, "test")
    assert (storage.run_dir(data["id"]) / "source.xlsx").read_bytes() == upload[1]
    # 模板的测试样本只给试发、样本试跑用，正式任务不碰它。
    assert storage.prompt_file(PROMPT_ID, "excel").read_bytes() == sample


async def test_limit_covering_every_row_is_a_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _online(monkeypatch, release())
    data = await batch_runs.start_run(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        FULL_ACCESS,
        {"prompt_id": PROMPT_ID, "limit": 10},
        upload=("a.xlsx", xlsx([["名称"], ["甲"], ["乙"]])),
    )
    assert (data["total_count"], data["row_limit"], data["run_mode"]) == (2, 0, "all")


async def test_unreleased_template_cannot_start_a_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _online(monkeypatch, None)
    with pytest.raises(ApiError, match="还没有上线"):
        await batch_runs.preview_input(FakeSession(), FULL_ACCESS, PROMPT_ID, ("a.xlsx", xlsx([["名称"], ["甲"]])))  # type: ignore[arg-type]


async def test_preview_reports_release_and_model_without_creating_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    added = _online(monkeypatch, release())
    summary = await batch_runs.preview_input(
        FakeSession(),  # type: ignore[arg-type]
        FULL_ACCESS,
        PROMPT_ID,
        ("数据.xlsx", xlsx([["名称", "备注"], ["甲", ""], ["乙", ""]])),
    )
    assert summary == {
        "name": "数据.xlsx",
        "rows": 2,
        "headers": ["名称", "备注"],
        "release_no": 3,
        "model_name": "百度-DeepSeek-V3.2",
    }
    assert added == []


async def test_running_task_is_reported_before_the_file_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _online(monkeypatch, release())

    async def busy(*_: Any, **__: Any) -> Any:
        return run(status="running", done_count=3, total_count=9)

    monkeypatch.setattr(repo, "active_for_prompt", busy)
    with pytest.raises(ApiError) as conflict:
        await batch_runs.preview_input(FakeSession(), FULL_ACCESS, PROMPT_ID, ("坏文件.xlsx", b"not excel"))  # type: ignore[arg-type]
    assert conflict.value.http_status == 409 and "3/9" in conflict.value.message


async def test_release_code_table_is_frozen_into_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _online(monkeypatch, release(code_table="scenarios"))

    async def fetch(_name: str) -> str:
        return "一级行业\t一级场景\n教育行业\t智慧校园"

    monkeypatch.setattr(releases, "fetch_code_table", fetch)
    data = await batch_runs.start_run(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        FULL_ACCESS,
        {"prompt_id": PROMPT_ID},
        upload=("a.xlsx", xlsx([["名称"], ["甲"]])),
    )
    code = storage.run_dir(data["id"]) / storage.PROMPT_FILES["code"]
    assert code.read_text(encoding="utf-8").endswith("智慧校园")


@pytest.mark.parametrize(
    "name,rows,message",
    [
        ("data.csv", [["名称"], ["甲"]], ".xlsx"),
        ("data.xlsx", [["草稿列"], ["甲"]], "缺少模板引用的列：名称"),
        ("data.xlsx", [["名称"]], "没有数据行"),
    ],
)
async def test_invalid_input_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, rows: list[list[str]], message: str
) -> None:
    _online(monkeypatch, release())
    with pytest.raises(ApiError, match=message):
        await batch_runs.preview_input(FakeSession(), FULL_ACCESS, PROMPT_ID, (name, xlsx(rows)))  # type: ignore[arg-type]


async def test_read_only_category_cannot_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    _online(monkeypatch, release())
    access = CategoryAccess(readable=frozenset({"policy"}), editable=frozenset())
    with pytest.raises(PermissionDeniedError):
        await batch_runs.preview_input(FakeSession(), access, PROMPT_ID, ("data.xlsx", xlsx([["名称"], ["甲"]])))  # type: ignore[arg-type]
