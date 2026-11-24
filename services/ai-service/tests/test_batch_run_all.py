"""先跑前几行、满意了再跑全部：同一份数据、同一版冻结的提示词，前面答好的行沿用。"""

from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError

from app.application import batch_run_all
from app.application.batch_output import RowResult, append_raw, read_raw, start_raw
from app.core import storage
from app.domain.categories import FULL_ACCESS, CategoryAccess
from app.repositories import batch_runs as repo
from app.repositories import prompts as prompt_repo
from tests.helpers import ACTOR, RUN_ID, FakeSession, noop, run, template, xlsx

GOOD = '[{"行业":"制造"}]'


@pytest.fixture
def tested(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """只跑了前 2 行的任务：第 1 行答好了，第 2 行失败。数据有 4 行。"""

    item = run(status="done", row_limit=2, total_count=2, output_fields="行业", prompt_content="企业：@【名称】")
    run_dir = storage.run_dir(item.id)
    storage.remove_tree(run_dir)
    storage.write_atomic(run_dir / "source.xlsx", xlsx([["名称"], ["甲"], ["乙"], ["丙"], ["丁"]]))
    storage.write_atomic(run_dir / "code.txt", "码表".encode())
    raw = storage.run_file(item.id, "raw")
    start_raw(raw)
    append_raw(raw, RowResult("a1000001", "问", GOOD, 10, 5, 0, "", 0.1).raw_row("模型"))
    append_raw(raw, RowResult("a1000002", "问", "", 0, 0, 0, "超时", 0.1).raw_row("模型"))
    state: dict[str, Any] = {"prompt": template(), "active": None, "locks": []}

    async def get(_session: Any, run_id: str, *, lock: bool = False, **_: Any) -> Any:
        state["locks"].append(lock)
        return item if run_id == item.id else None

    async def get_prompt(*_: Any, **__: Any) -> Any:
        return state["prompt"]

    async def active(*_: Any, **__: Any) -> Any:
        return state["active"]

    async def model(*_: Any, **__: Any) -> Any:
        return type("Model", (), {"id": item.model_id, "name": item.model_name})()

    events: list[dict[str, Any]] = []

    async def audit(*_: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    added: list[Any] = []
    monkeypatch.setattr(repo, "get", get)
    monkeypatch.setattr(repo, "add", lambda _session, value: added.append(value))
    monkeypatch.setattr(repo, "active_for_prompt", active)
    monkeypatch.setattr(prompt_repo, "get", get_prompt)
    monkeypatch.setattr(batch_run_all, "reconcile_stale", noop)
    monkeypatch.setattr(batch_run_all, "resolve_model", model)
    monkeypatch.setattr(batch_run_all, "enqueue_event", audit)
    return {"run": item, "added": added, "events": events, "state": state}


async def test_run_all_reuses_the_answered_rows_and_the_frozen_inputs(tested: dict[str, Any]) -> None:
    data = await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    new = tested["added"][0]
    assert (data["reused_rows"], new.row_limit, new.total_count, new.status) == (1, 0, 4, "queued")
    assert (new.prompt_content, new.output_fields) == ("企业：@【名称】", "行业")
    target = storage.run_dir(new.id)
    assert (target / "code.txt").read_text(encoding="utf-8") == "码表"
    assert (target / "source.xlsx").read_bytes() == (storage.run_dir(RUN_ID) / "source.xlsx").read_bytes()
    # 只抄答好的那行；失败的第 2 行留给新任务重问。
    assert list(read_raw(storage.run_file(new.id, "raw"))) == ["a1000001"]
    assert tested["events"][0]["changes"]["from_run"] == RUN_ID
    storage.remove_tree(target)


async def test_only_finished_partial_page_runs_can_run_all(tested: dict[str, Any]) -> None:
    item = tested["run"]
    item.row_limit = 0
    with pytest.raises(ApiError, match="只跑了前几行"):
        await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    item.row_limit, item.status = 2, "running"
    with pytest.raises(ApiError, match="还没跑完"):
        await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    item.status, item.source = "done", "sample"
    with pytest.raises(NotFoundError):
        await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    item.source = "manual"
    storage.remove_tree(storage.run_dir(RUN_ID))
    with pytest.raises(ApiError, match="没有保存数据文件"):
        await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert tested["added"] == []


async def test_run_all_works_after_prompt_deleted_or_reclassified_and_checks_permission_first(
    tested: dict[str, Any],
) -> None:
    """模板已删除或已迁到其他分类时，已冻结快照的测试任务仍可跑全部；无当前任务分类编辑权限时先报 403。"""

    item = tested["run"]
    item.row_limit = 0
    read_only = CategoryAccess(readable=frozenset({item.prompt_category}), editable=frozenset())
    with pytest.raises(PermissionDeniedError):
        await batch_run_all.run_all(FakeSession(), ACTOR, read_only, RUN_ID)  # type: ignore[arg-type]

    item.row_limit = 2
    tested["state"]["active"] = run(status="running", done_count=1, total_count=4)
    with pytest.raises(ApiError, match="已有任务在运行"):
        await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]

    # 模板已被删除，仍能按冻结快照发起跑全部，且对原任务记录加行锁防止并发重复发起或删除
    tested["state"]["active"] = None
    tested["state"]["prompt"] = None
    tested["state"]["locks"].clear()
    policy_editor = CategoryAccess(
        readable=frozenset({item.prompt_category}), editable=frozenset({item.prompt_category})
    )
    data = await batch_run_all.run_all(FakeSession(), ACTOR, policy_editor, RUN_ID)  # type: ignore[arg-type]
    assert tested["state"]["locks"] == [True]
    assert data["reused_rows"] == 1 and tested["added"][0].total_count == 4
    storage.remove_tree(storage.run_dir(tested["added"][0].id))


async def test_run_all_reconciles_stale_source_run_before_status_check(
    tested: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """原测试任务因 worker 异常中断停在 running 时，先由 reconcile_stale 纠正为 interrupted 再允许跑全部。"""

    item = tested["run"]
    item.status = "running"

    async def mark_interrupted(_session: Any) -> None:
        item.status = "interrupted"

    monkeypatch.setattr(batch_run_all, "reconcile_stale", mark_interrupted)
    data = await batch_run_all.run_all(FakeSession(), ACTOR, FULL_ACCESS, RUN_ID)  # type: ignore[arg-type]
    assert data["status"] == "queued" and tested["added"][0].total_count == 4
    storage.remove_tree(storage.run_dir(tested["added"][0].id))
