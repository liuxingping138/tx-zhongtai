"""2026-10-27 巡检发现的几处：看门狗不能死、定时任务批次不可重跑、停用模型的提示、旧系统导入覆盖、
内部状态接口先纠正中断。"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.errors import ApiError

from app.application import asking, batch_execute, batch_runs, pipeline_runs
from app.application.legacy_import import _overwrite
from app.core import storage
from app.domain.models import RUN_SOURCE_PIPELINE, PromptTemplate
from tests.helpers import RUN_ID, FakeSession, run, xlsx


def test_pipeline_batches_cannot_be_retried_from_the_page() -> None:
    """定时任务的批次由政策服务取结果，页面重跑没人消费、只会再花钱。"""

    storage.write_atomic(storage.run_dir(RUN_ID) / "source.xlsx", xlsx([["名称"], ["甲"]]))
    manual = run(status="done", total_count=3, done_count=2, failed_count=1)
    pipeline = run(status="done", total_count=3, done_count=2, failed_count=1, source=RUN_SOURCE_PIPELINE)
    assert batch_runs._can_retry(manual) is True
    assert batch_runs._can_retry(pipeline) is False and batch_runs.to_dict(pipeline)["can_retry"] is False


async def test_watchdog_survives_a_database_hiccup(monkeypatch: pytest.MonkeyPatch) -> None:
    """心跳协程一死任务就会被误判中断、停止按钮失效：库连接炸一次要能接着跑。"""

    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _Broken(_Session):
        async def __aenter__(self) -> _Session:
            raise RuntimeError("connection reset")

    sessions = iter([_Broken(), _Session(), _Session()])
    beats: list[str] = []

    async def update_fields(_session: Any, run_id: str, _values: dict[str, Any]) -> None:
        beats.append(run_id)

    async def cancel_flag(_session: Any, _run_id: str) -> bool:
        return len(beats) >= 2

    monkeypatch.setattr(batch_execute, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(batch_execute, "PROGRESS_SECONDS", 0)
    monkeypatch.setattr(batch_execute, "_progress", lambda _job: {})
    monkeypatch.setattr(batch_execute.repo, "update_fields", update_fields)
    monkeypatch.setattr(batch_execute.repo, "cancel_flag", cancel_flag)
    job = SimpleNamespace(run=SimpleNamespace(id="r1"), stop=asyncio.Event())
    watcher = asyncio.create_task(batch_execute._watch(job))  # type: ignore[arg-type]
    await asyncio.wait_for(job.stop.wait(), timeout=2)
    watcher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher
    assert beats == ["r1", "r1"]  # 炸的那次没心跳，后面两次正常，停止标志也认到了


async def test_disabled_model_message_says_where_to_fix_it(model_table: list[Any]) -> None:
    model_table[0].enabled = False
    with pytest.raises(ApiError, match="已停用，请换一个模型"):
        await asking.resolve_model(FakeSession(), model_table[0].id)  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="已停用，它是上线版本用的模型，请改模板的模型后重新上线"):
        await asking.resolve_model(FakeSession(), model_table[0].id, frozen=asking.RELEASE_MODEL_DISABLED)  # type: ignore[arg-type]


def test_legacy_overwrite_only_touches_columns_the_import_set() -> None:
    """旧库导出里没有类型、码表、上线版本：覆盖时不能把它们冲成 None（撞 NOT NULL，已上线的被下线）。"""

    existing = PromptTemplate(
        id="p", title="旧", content="旧内容", category="policy", code_table="policy_types", release_id="r1"
    )
    fresh = PromptTemplate(id="p", title="新", content="新内容")
    _overwrite(existing, fresh, keep=("id",))
    assert (existing.title, existing.content) == ("新", "新内容")
    assert (existing.category, existing.code_table, existing.release_id) == ("policy", "policy_types", "r1")


async def test_internal_status_corrects_stale_runs_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 被强杀后没心跳的任务要先纠正成「中断」，政策服务才不会一直轮询到自己超时。"""

    calls: list[str] = []

    async def reconcile(_session: Any) -> int:
        calls.append("reconcile")
        return 0

    async def require(_session: Any, _run_id: str) -> Any:
        calls.append("require")
        return run()

    monkeypatch.setattr(batch_runs, "reconcile_stale", reconcile)
    monkeypatch.setattr(pipeline_runs, "require_run", require)
    await pipeline_runs.status(FakeSession(), RUN_ID)  # type: ignore[arg-type]
    assert calls == ["reconcile", "require"]
