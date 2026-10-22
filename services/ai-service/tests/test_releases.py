from __future__ import annotations

from typing import Any

import httpx
import pytest
from platform_common.errors import ApiError, DependencyUnavailableError

from app.application import batch_runs, prompts, releases
from app.core import codebook, storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS
from app.domain.models import TemplateRelease
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as prompt_repo
from app.repositories import releases as release_repo
from tests.helpers import ACTOR, PROMPT_ID, FakeSession, noop, template, xlsx

READY = {"output_fields": "政策类型名称", "model_id": "baidu-deepseek-v3.2"}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def record(_: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(releases, "enqueue_event", record)
    monkeypatch.setattr(batch_runs, "enqueue_event", noop)
    monkeypatch.setattr(get_settings(), "baidu_api_key", "k")
    return events


def _tables(monkeypatch: pytest.MonkeyPatch, item: Any, saved: list[TemplateRelease]) -> None:
    async def get(*_: Any, **__: Any) -> Any:
        return item

    async def last_no(*_: Any) -> int:
        return max((release.release_no for release in saved), default=0)

    async def by_ids(_session: Any, ids: list[str]) -> dict[str, TemplateRelease]:
        return {release.id: release for release in saved if release.id in ids}

    monkeypatch.setattr(prompt_repo, "get", get)
    monkeypatch.setattr(release_repo, "last_no", last_no)
    monkeypatch.setattr(release_repo, "by_ids", by_ids)
    monkeypatch.setattr(release_repo, "add", lambda _session, release: saved.append(release))


def _codebook(monkeypatch: pytest.MonkeyPatch, text: str = "政策类型名称\n信息化建设类") -> list[str]:
    asked: list[str] = []

    async def fetch(name: str) -> str:
        asked.append(name)
        return text

    for module in (prompts, releases):
        monkeypatch.setattr(module, "fetch_code_table", fetch)
    return asked


async def test_publish_requires_output_fields_and_a_fixed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """定时任务没人盯：没有输出字段、没定模型的模板上线就会整批跑废。"""

    saved: list[TemplateRelease] = []
    _tables(monkeypatch, template(output_fields=""), saved)
    with pytest.raises(ApiError, match="输出字段"):
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    _tables(monkeypatch, template(output_fields="行业", model_id=""), saved)
    with pytest.raises(ApiError, match="选定模型"):
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert saved == []


async def test_publish_freezes_a_numbered_version_and_drafts_show_unreleased_changes(
    monkeypatch: pytest.MonkeyPatch, _quiet: list[dict[str, Any]]
) -> None:
    item = template(code_table="policy_types", **READY)
    saved: list[TemplateRelease] = []
    _tables(monkeypatch, item, saved)
    asked = _codebook(monkeypatch)
    first = await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert asked == ["policy_types"]  # 上线前确认系统码表取得到
    assert (first["release"]["release_no"], first["release"]["unreleased_changes"]) == (1, [])
    assert item.release_id == saved[0].id and _quiet[-1]["changes"] == {"release_no": 1}

    item.content, item.code_table = "改过的提示词", "scenarios"
    draft = await prompts.to_out(FakeSession(), item, FULL_ACCESS)  # type: ignore[arg-type]
    assert draft["release"]["unreleased_changes"] == ["提示词内容", "码表"]
    second = await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert second["release"]["release_no"] == 2 and saved[0].content != saved[1].content


async def test_online_template_cannot_be_deleted_and_offline_needs_a_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "enqueue_event", noop)
    saved: list[TemplateRelease] = []
    _tables(monkeypatch, template(release_id="c" * 32), saved)
    with pytest.raises(ApiError, match="先下线"):
        await prompts.delete_prompt(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    offline = await releases.take_offline(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert offline["release"] is None
    with pytest.raises(ApiError, match="还没有上线"):
        await releases.take_offline(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]


async def test_system_code_table_is_fetched_live_and_frozen_into_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """系统码表每次实时取；发起批量时把那一刻的内容写进任务快照，之后码表再改也不影响这次任务和它的重跑。"""

    item = template(excel_name="a.xlsx", code_table="scenarios", code_name="旧码表.txt")
    _tables(monkeypatch, item, [])
    asked = _codebook(monkeypatch, "一级行业\t一级场景\n教育行业\t智慧校园")

    async def idle(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(run_repo, "active_for_prompt", idle)
    monkeypatch.setattr(run_repo, "mark_stale_interrupted", idle)
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲"]]))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), "上传的旧码表".encode())
    assert await prompts.code_text(item) == "一级行业\t一级场景\n教育行业\t智慧校园"
    run = await batch_runs.start_run(
        FakeSession(),
        ACTOR,
        FULL_ACCESS,
        {"prompt_id": PROMPT_ID, "model_id": "baidu-deepseek-v3.2"},  # type: ignore[arg-type]
    )
    snapshot = storage.run_dir(run["id"]) / storage.PROMPT_FILES["code"]
    assert snapshot.read_text(encoding="utf-8").endswith("智慧校园") and asked == ["scenarios", "scenarios"]
    item.code_table = ""
    assert await prompts.code_text(item) == "上传的旧码表"


async def test_codebook_client_never_falls_back_to_an_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """取不到码表就报错：拿空码表提问，模型照样回答，结果全错还看不出来。"""

    monkeypatch.setattr(get_settings(), "codebook_service_secret", "")
    with pytest.raises(DependencyUnavailableError, match="未配置"):
        await codebook.fetch_code_table("policy_types")

    def refuse(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-internal-service"] == "ai-service"
        return httpx.Response(401, json={"code": "INTERNAL_CALLER_REJECTED"})

    real = httpx.AsyncClient
    monkeypatch.setattr(get_settings(), "codebook_service_secret", "s")
    monkeypatch.setattr(codebook.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(refuse), **kw))
    with pytest.raises(DependencyUnavailableError, match="401"):
        await codebook.fetch_code_table("policy_types")
