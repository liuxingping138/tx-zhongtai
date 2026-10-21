from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import ApiError, NotFoundError

from app.application import asking
from app.application import prompts as service
from app.core import storage
from app.core.config import get_settings
from app.repositories import prompts as repo
from tests.helpers import ACTOR, PROMPT_ID, FakeSession, fake_stream, noop, template, xlsx


@pytest.fixture(autouse=True)
def _quiet_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def record(_: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service, "enqueue_event", record)
    return events


def _use(monkeypatch: pytest.MonkeyPatch, item: Any) -> None:
    async def get(*_: Any, **__: Any) -> Any:
        return item

    monkeypatch.setattr(repo, "get", get)


async def test_create_validates_and_normalizes_fields(_quiet_audit: list[dict[str, Any]]) -> None:
    session = FakeSession()
    data = await service.create_prompt(
        session,
        ACTOR,
        {"title": " 标题 ", "content": "内容", "output_fields": "行业| |场景", "model_id": "x"},  # type: ignore[arg-type]
    )
    assert (data["title"], data["output_fields"], data["fields"]) == ("标题", "行业|场景", ["行业", "场景"])
    assert data["created_by_name"] == "测试员" and len(data["id"]) == 32
    assert _quiet_audit[0]["event_type"] == "ai.prompt.created"
    with pytest.raises(ApiError, match="标题不能为空"):
        await service.create_prompt(session, ACTOR, {"title": "", "content": "x"})  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="内容不能为空"):
        await service.create_prompt(session, ACTOR, {"title": "t", "content": " "})  # type: ignore[arg-type]


async def test_update_rejects_stale_version_and_records_changed_fields(
    monkeypatch: pytest.MonkeyPatch, _quiet_audit: list[dict[str, Any]]
) -> None:
    item = template()
    _use(monkeypatch, item)
    with pytest.raises(ApiError) as conflict:
        await service.update_prompt(FakeSession(), ACTOR, PROMPT_ID, {"title": "新", "content": "c", "version": 9})  # type: ignore[arg-type]
    assert conflict.value.http_status == 409
    data = await service.update_prompt(
        FakeSession(),
        ACTOR,
        PROMPT_ID,
        {"title": "新标题", "content": item.content, "version": 1},  # type: ignore[arg-type]
    )
    assert data["version"] == 2 and data["title"] == "新标题"
    assert _quiet_audit[-1]["changes"] == {"fields": ["model_id", "output_fields", "title"]}


async def test_missing_or_malformed_ids_are_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, None)
    with pytest.raises(NotFoundError):
        await service.require(FakeSession(), PROMPT_ID)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await service.require(FakeSession(), "../../etc")  # type: ignore[arg-type]


async def test_excel_and_code_uploads_are_stored_and_summarized(monkeypatch: pytest.MonkeyPatch) -> None:
    item = template()
    _use(monkeypatch, item)
    data = await service.upload_file(
        FakeSession(),
        ACTOR,
        PROMPT_ID,
        "excel",
        "C:\\fakepath\\企业.xlsx",
        xlsx([["名称"], ["甲"], ["乙"]]),  # type: ignore[arg-type]
    )
    assert (data["excel_name"], data["excel_rows"], data["excel_headers"]) == ("企业.xlsx", 2, ["名称"])
    assert storage.prompt_file(PROMPT_ID, "excel").is_file()
    data = await service.upload_file(FakeSession(), ACTOR, PROMPT_ID, "code", "码表.txt", "编码".encode("gbk"))  # type: ignore[arg-type]
    assert storage.prompt_file(PROMPT_ID, "code").read_text(encoding="utf-8") == "编码"
    content, name = await service.download_file(FakeSession(), ACTOR, PROMPT_ID, "code")  # type: ignore[arg-type]
    assert (content.decode(), name) == ("编码", "码表.txt")
    with pytest.raises(ApiError, match=r"只支持 \.xlsx"):
        await service.upload_file(FakeSession(), ACTOR, PROMPT_ID, "excel", "a.xls", b"x")  # type: ignore[arg-type]
    data = await service.delete_file(FakeSession(), ACTOR, PROMPT_ID, "code")  # type: ignore[arg-type]
    assert data["code_name"] == "" and not storage.prompt_file(PROMPT_ID, "code").exists()
    with pytest.raises(NotFoundError):
        await service.download_file(FakeSession(), ACTOR, PROMPT_ID, "code")  # type: ignore[arg-type]


async def test_delete_removes_template_files(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, template())
    monkeypatch.setattr(repo, "delete", noop)
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), b"x")
    await service.delete_prompt(FakeSession(), ACTOR, PROMPT_ID)  # type: ignore[arg-type]
    assert not storage.prompt_dir(PROMPT_ID).exists()


async def test_list_returns_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def items(*_: Any) -> list[Any]:
        return [template()]

    monkeypatch.setattr(repo, "list_all", items)
    assert [item["title"] for item in await service.list_prompts(FakeSession())] == ["企业行业"]  # type: ignore[arg-type]


def _with_keys(monkeypatch: pytest.MonkeyPatch, ark: str = "", baidu: str = "") -> None:
    monkeypatch.setattr(get_settings(), "ark_api_key", ark)
    monkeypatch.setattr(get_settings(), "baidu_api_key", baidu)


async def test_trial_fills_variables_from_first_row_and_code_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_keys(monkeypatch, baidu="k")
    _use(monkeypatch, template(excel_name="a.xlsx", code_name="c.txt"))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲公司"], ["乙公司"]]))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), b"A\tB")
    model, prompt = await asking.prepare_trial(
        FakeSession(),
        content="@【名称】/@【上传码表】",
        model_id="baidu-deepseek-v3.2",
        prompt_id=PROMPT_ID,  # type: ignore[arg-type]
    )
    assert (model.id, prompt) == ("baidu-deepseek-v3.2", "甲公司/A\tB")


async def test_models_require_configured_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_keys(monkeypatch, ark="k")
    available = {item["id"]: item["available"] for item in await asking.available_models(FakeSession())}  # type: ignore[arg-type]
    assert available["deepseek-v4-flash"] is True and available["baidu-deepseek-v3.2"] is False
    with pytest.raises(ApiError) as missing:
        await asking.prepare_chat(FakeSession(), "baidu-deepseek-v3.2", "hi")
    assert missing.value.http_status == 503
    with pytest.raises(ApiError, match="未知模型"):
        await asking.prepare_chat(FakeSession(), "nope", "hi")
    with pytest.raises(ApiError, match="不能为空"):
        await asking.prepare_chat(FakeSession(), "deepseek-v4-flash", "  ")


async def test_stream_answer_echoes_prompt_then_model_events_then_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_keys(monkeypatch, ark="k")
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": "答"}, {"response_id": "r1"}]))
    model, message = await asking.prepare_chat(FakeSession(), "deepseek-v4-flash", "问")
    chunks = [chunk async for chunk in asking.stream_answer(model, message, thinking=False, echo_prompt=True)]
    assert chunks[0] == 'data: {"prompt": "问"}\n\n'
    assert chunks[1].startswith('data: {"model": {"id": "deepseek-v4-flash"')
    assert chunks[2:] == ['data: {"text": "答"}\n\n', 'data: {"response_id": "r1"}\n\n', "data: [DONE]\n\n"]
