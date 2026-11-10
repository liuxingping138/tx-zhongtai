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
from app.repositories import prompts as prompt_repo
from app.repositories import releases as release_repo
from tests.helpers import ACTOR, PROMPT_ID, FakeSession, noop, template

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
    _tables(monkeypatch, template(content=" "), saved)
    with pytest.raises(ApiError, match="写好提示词"):
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    _tables(monkeypatch, template(output_fields=""), saved)
    with pytest.raises(ApiError, match="输出字段"):
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    _tables(monkeypatch, template(output_fields="行业", model_id=""), saved)
    with pytest.raises(ApiError, match="选定模型"):
        await releases.publish(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    _tables(monkeypatch, template(content="用@【上传码表】分类", **READY), saved)
    with pytest.raises(ApiError, match="码表是空的"):
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


async def test_system_code_table_is_fetched_live(monkeypatch: pytest.MonkeyPatch) -> None:
    """系统码表每次实时取；上传的码表只在没选系统码表时用。发起批量时冻结的那份见 test_batch_inputs。"""

    item = template(excel_name="a.xlsx", code_table="scenarios", code_name="旧码表.txt")
    _tables(monkeypatch, item, [])
    _codebook(monkeypatch, "一级行业\t一级场景\n教育行业\t智慧校园")
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), "上传的旧码表".encode())
    assert await prompts.code_text(item) == "一级行业\t一级场景\n教育行业\t智慧校园"
    item.code_table = ""
    assert await prompts.code_text(item) == "上传的旧码表"


async def test_code_preview_says_how_big_and_shows_the_first_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """选码表时就能看内容：系统码表实时取、上传的读文件；整份多大写清楚，只回前 200 行。"""

    table = "\n".join(f"行业{index}\t场景{index}" for index in range(250))
    _codebook(monkeypatch, table)
    data = await prompts.preview_system_code("scenario_l1")
    assert (data["name"], data["lines"], data["chars"], data["truncated"]) == (
        "行业场景码表（一级行业 + 一级场景）",
        250,
        len(table),
        True,
    )
    assert data["head"].splitlines() == table.splitlines()[:200]
    for key, message in (("", "先选一个系统码表"), ("nope", "不认识的系统码表")):
        with pytest.raises(ApiError, match=message):
            await prompts.preview_system_code(key)

    _tables(monkeypatch, template(code_name="码表.txt"), [])
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), b"A\tB\nC\tD")
    uploaded = await prompts.preview_uploaded_code(FakeSession(), FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert (uploaded["name"], uploaded["lines"], uploaded["chars"], uploaded["truncated"]) == ("码表.txt", 2, 7, False)
    _tables(monkeypatch, template(code_name=""), [])
    with pytest.raises(ApiError, match="还没上传码表"):
        await prompts.preview_uploaded_code(FakeSession(), FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]


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


def test_reuploading_a_code_table_with_the_same_name_counts_as_a_change() -> None:
    """按提示重传同名的「码表.txt」：原来只比文件名，算没改动，上线入口不出现，定时任务一直用旧码表。"""

    from app.domain.code_tables import code_digest
    from app.domain.models import PromptTemplate, TemplateRelease
    from app.domain.releases import unreleased_changes

    same = {"title": "t", "category": "policy", "content": "c", "output_fields": "f", "model_id": "m", "code_table": ""}
    release = TemplateRelease(**same, code_name="码表.txt", code_digest=code_digest(b"old"))
    template = PromptTemplate(**same, code_name="码表.txt", code_digest=code_digest(b"old"))
    assert unreleased_changes(template, release) == []
    template.code_digest = code_digest(b"new")
    assert unreleased_changes(template, release) == ["码表"]
    # 摘要功能上线前的版本没有摘要：重传一次就算改动，多提示一次重新上线，不悄悄沿用旧码表。
    release.code_digest = ""
    assert unreleased_changes(template, release) == ["码表"]
