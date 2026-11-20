"""2026-10-27 巡检发现的几处：看门狗不能死、定时任务批次不可重跑、停用模型的提示、旧系统导入覆盖、
内部状态接口先纠正中断。"""

from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.clock import utcnow
from platform_common.errors import ApiError

from app.application import asking, batch_execute, batch_runs, pipeline_runs, row_asking
from app.application.legacy_import import _overwrite
from app.application.run_costs import Ledger, Spend
from app.core import storage
from app.domain.models import RUN_SOURCE_PIPELINE, PromptTemplate
from app.repositories import batch_runs as run_repo
from tests.helpers import ACTOR, RUN_ID, FakeSession, run, xlsx


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

    async def update_fields(_session: Any, run_id: str, _values: dict[str, Any], also: Any = ()) -> bool:
        beats.append(run_id)
        return True

    async def cancel_flag(_session: Any, _run_id: str) -> bool:
        return len(beats) >= 2

    monkeypatch.setattr(batch_execute, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(batch_execute, "PROGRESS_SECONDS", 0)
    monkeypatch.setattr(batch_execute, "_progress", lambda _job: {})
    monkeypatch.setattr(batch_execute.repo, "update_if_running", update_fields)
    monkeypatch.setattr(batch_execute.repo, "cancel_flag", cancel_flag)
    booked: list[dict[Any, Any]] = []

    async def book(_session: Any, _run_id: str, taken: dict[Any, Any]) -> None:
        booked.append(dict(taken))

    monkeypatch.setattr(batch_execute, "book", book)
    ledger = Ledger()
    ledger.add(utcnow(), Spend(1, 1, 0, Decimal("0.5"), Decimal(0)))
    job = SimpleNamespace(run=SimpleNamespace(id="r1"), stop=asyncio.Event(), ledger=ledger)
    watcher = asyncio.create_task(batch_execute._watch(job))  # type: ignore[arg-type]
    await asyncio.wait_for(job.stop.wait(), timeout=2)
    watcher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher
    assert beats == ["r1", "r1"]  # 炸的那次没心跳，后面两次正常，停止标志也认到了
    # 炸的那次没记上的花费放回去了，下一次记上，只记一次。
    assert [sum(spend.inference_cost for spend in item.values()) for item in booked] == [Decimal("0.5"), 0]


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

    async def found(*_args: Any, **_kwargs: Any) -> Any:
        return run()

    monkeypatch.setattr(run_repo, "get", found)
    await pipeline_runs.status(FakeSession(), RUN_ID, ACTOR)  # type: ignore[arg-type]
    assert calls == ["reconcile", "require"]


async def test_a_run_marked_interrupted_stops_asking_and_does_not_overwrite_a_requeued_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """心跳断过一阵、任务被纠正成「中断」后 worker 还活着：停止按钮已经没了，它不停就一直花钱；
    人又点了重跑排回队列的话，这次执行的收尾也不能把排队状态盖掉。"""

    from tests.test_batch import _prepare_execution, _Recorder

    recorder = _Recorder()
    _prepare_execution(monkeypatch, recorder, run())
    monkeypatch.setattr(batch_execute, "PROGRESS_SECONDS", 0)
    asked: list[int] = []

    async def slow(*_: Any, **__: Any) -> Any:
        asked.append(1)
        recorder.running = False  # 第一行问着的时候，库里已经不是运行中了
        await asyncio.sleep(0.05)
        yield {"text": '[{"行业":"制造"}]'}

    monkeypatch.setattr(row_asking, "stream_responses", slow)
    await batch_execute.execute(RUN_ID)
    assert len(asked) < 3
    assert not any("status" in update for update in recorder.updates)
