from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError

from app.application import asking, test_rows
from app.application import prompts as service
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import FULL_ACCESS, CategoryAccess
from app.domain.models import RUN_SOURCE_SAMPLE
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as repo
from tests.helpers import ACTOR, PROMPT_ID, FakeSession, fake_stream, noop, run, template, xlsx


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
        FULL_ACCESS,
        {"title": " 标题 ", "category": "policy", "content": "内容", "output_fields": "行业| |场景", "model_id": "x"},  # type: ignore[arg-type]
    )
    assert (data["title"], data["output_fields"], data["fields"]) == ("标题", "行业|场景", ["行业", "场景"])
    assert data["created_by_name"] == "测试员" and len(data["id"]) == 32
    assert _quiet_audit[0]["event_type"] == "ai.prompt.created"
    with pytest.raises(ApiError, match="标题不能为空"):
        await service.create_prompt(session, ACTOR, FULL_ACCESS, {"title": "", "category": "policy", "content": "x"})  # type: ignore[arg-type]
    # 提示词可以先空着：新模板先传测试样本、选码表，再照着列名写；试跑和上线时才要求写好。
    draft = await service.create_prompt(
        session,
        ACTOR,
        FULL_ACCESS,
        {"title": "t", "category": "policy", "content": " "},  # type: ignore[arg-type]
    )
    assert draft["content"] == ""


async def test_update_rejects_stale_version_and_records_changed_fields(
    monkeypatch: pytest.MonkeyPatch, _quiet_audit: list[dict[str, Any]]
) -> None:
    item = template()
    _use(monkeypatch, item)
    with pytest.raises(ApiError) as conflict:
        await service.update_prompt(
            FakeSession(),
            ACTOR,
            FULL_ACCESS,
            PROMPT_ID,
            {"title": "新", "category": "policy", "content": "c", "version": 9},
        )  # type: ignore[arg-type]
    assert conflict.value.http_status == 409
    data = await service.update_prompt(
        FakeSession(),
        ACTOR,
        FULL_ACCESS,
        PROMPT_ID,
        {"title": "新标题", "category": "policy", "content": item.content, "version": 1},  # type: ignore[arg-type]
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
        FULL_ACCESS,
        PROMPT_ID,
        "excel",
        ("C:\\fakepath\\企业.xlsx", xlsx([["名称"], ["甲"], ["乙"]])),  # type: ignore[arg-type]
    )
    assert (data["excel_name"], data["excel_rows"], data["excel_headers"]) == ("企业.xlsx", 2, ["名称"])
    assert storage.prompt_file(PROMPT_ID, "excel").is_file()
    data = await service.upload_file(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        FULL_ACCESS,
        PROMPT_ID,
        "code",
        ("码表.txt", "编码".encode("gbk")),
    )
    assert storage.prompt_file(PROMPT_ID, "code").read_text(encoding="utf-8") == "编码"
    content, name = await service.download_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code")  # type: ignore[arg-type]
    assert (content.decode(), name) == ("编码", "码表.txt")
    with pytest.raises(ApiError, match=r"只支持 \.xlsx"):
        await service.upload_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "excel", ("a.xls", b"x"))  # type: ignore[arg-type]
    data = await service.delete_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code")  # type: ignore[arg-type]
    assert data["code_name"] == "" and not storage.prompt_file(PROMPT_ID, "code").exists()
    with pytest.raises(NotFoundError):
        await service.download_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code")  # type: ignore[arg-type]


async def test_code_table_can_be_an_excel_or_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Excel 码表转成和系统码表一样的文字：一行一条、Tab 分隔、空行跳过；下载回去是 .txt。"""

    _use(monkeypatch, template())
    book = xlsx([["一级行业", "一级场景", None], ["交通行业", "智慧航空"], [None, None], ["能源行业", "智慧水务", " "]])
    data = await service.upload_file(
        FakeSession(),  # type: ignore[arg-type]
        ACTOR,
        FULL_ACCESS,
        PROMPT_ID,
        "code",
        ("行业场景.xlsx", book),
    )
    assert data["code_name"] == "行业场景.xlsx"
    expected = "一级行业\t一级场景\n交通行业\t智慧航空\n能源行业\t智慧水务"
    assert storage.prompt_file(PROMPT_ID, "code").read_text(encoding="utf-8") == expected
    content, name = await service.download_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code")  # type: ignore[arg-type]
    assert (content.decode(), name) == (expected, "行业场景.txt")

    await service.upload_file(
        FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code", ("码表.csv", "行业,场景".encode("gbk"))
    )  # type: ignore[arg-type]
    assert storage.prompt_file(PROMPT_ID, "code").read_text(encoding="utf-8") == "行业,场景"
    with pytest.raises(ApiError, match=r"只支持 \.txt、\.csv 或 \.xlsx"):
        await service.upload_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code", ("码表.xls", b"x"))  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="第一个工作表是空的"):
        await service.upload_file(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID, "code", ("空.xlsx", xlsx([[None]])))  # type: ignore[arg-type]


async def test_delete_removes_template_files_and_its_sample_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """样本试跑只属于这个模板：记录和产物一起删，不留孤儿文件；还在跑的先拦下。"""

    _use(monkeypatch, template())
    sample = run(id="e" * 32, source=RUN_SOURCE_SAMPLE, status="done")
    monkeypatch.setattr(repo, "delete", noop)
    monkeypatch.setattr(run_repo, "sample_runs_for_prompt", lambda _session, _prompt_id: _async([sample]))
    monkeypatch.setattr(run_repo, "active_for_prompt", lambda _session, _prompt_id, sources=(): _async(sample))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "code"), b"x")
    storage.write_atomic(storage.run_file(sample.id, "raw"), b"x")
    with pytest.raises(ApiError, match="样本试跑还没结束"):
        await service.delete_prompt(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert storage.prompt_dir(PROMPT_ID).exists()

    monkeypatch.setattr(run_repo, "active_for_prompt", lambda _session, _prompt_id, sources=(): _async(None))
    await service.delete_prompt(FakeSession(), ACTOR, FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert not storage.prompt_dir(PROMPT_ID).exists() and not storage.run_dir(sample.id).exists()
    # 试跑记录只打删除标记，花的钱仍算在费用账单里。
    assert sample.deleted_at is not None


async def _async(value: Any) -> Any:
    return value


async def test_list_only_queries_readable_categories_and_marks_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[set[str]] = []

    async def items(*_: Any, categories: frozenset[str]) -> list[Any]:
        asked.append(set(categories))
        return [template()]

    monkeypatch.setattr(repo, "list_all", items)
    reader = CategoryAccess(readable=frozenset({"policy", "tender"}), editable=frozenset({"tender"}))
    data = await service.list_prompts(FakeSession(), reader)  # type: ignore[arg-type]
    assert asked == [{"policy", "tender"}]
    assert [(item["title"], item["category_name"], item["editable"]) for item in data] == [("企业行业", "政策", False)]


def test_category_access_follows_grant_levels() -> None:
    access = CategoryAccess.from_levels({"ai.category.policy": "READ", "ai.category.tender": "FULL"})
    assert (access.readable, access.editable) == (frozenset({"policy", "tender"}), frozenset({"tender"}))
    assert access.options() == [
        {"code": "policy", "name": "政策", "editable": False},
        {"code": "tender", "name": "招投标", "editable": True},
    ]
    with pytest.raises(PermissionDeniedError, match="客户"):
        access.require_read("customer")


async def test_category_permission_guards_every_template_change(
    monkeypatch: pytest.MonkeyPatch, _quiet_audit: list[dict[str, Any]]
) -> None:
    """只读的类型不能新建、修改、上传、删除、试发；改类型时新旧两个类型都要有编辑权。"""

    _use(monkeypatch, template())
    reader = CategoryAccess(readable=frozenset({"policy"}), editable=frozenset({"tender"}))
    body = {"title": "t", "category": "policy", "content": "c", "version": 1}
    with pytest.raises(PermissionDeniedError):
        await service.create_prompt(FakeSession(), ACTOR, reader, body)  # type: ignore[arg-type]
    with pytest.raises(PermissionDeniedError):
        await service.update_prompt(FakeSession(), ACTOR, reader, PROMPT_ID, {**body, "category": "tender"})  # type: ignore[arg-type]
    with pytest.raises(PermissionDeniedError):
        await service.delete_prompt(FakeSession(), ACTOR, reader, PROMPT_ID)  # type: ignore[arg-type]
    with pytest.raises(PermissionDeniedError):
        await asking.prepare_trial(FakeSession(), reader, content="c", model_id="x", prompt_id=PROMPT_ID)  # type: ignore[arg-type]
    nobody = CategoryAccess(readable=frozenset(), editable=frozenset())
    with pytest.raises(PermissionDeniedError):
        await asking.prepare_trial(FakeSession(), nobody, content="c", model_id="x", prompt_id=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="模板类型"):
        await service.create_prompt(FakeSession(), ACTOR, FULL_ACCESS, {**body, "category": "其他"})  # type: ignore[arg-type]
    assert _quiet_audit == []


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
        FULL_ACCESS,
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
    chunks = [chunk async for chunk in asking.stream_answer(model, message, thinking=False, trial_fields=[])]
    assert chunks[0] == 'data: {"prompt": "问"}\n\n'
    assert chunks[1].startswith('data: {"model": {"id": "deepseek-v4-flash"')
    assert chunks[2:] == ['data: {"text": "答"}\n\n', 'data: {"response_id": "r1"}\n\n', "data: [DONE]\n\n"]


async def test_trial_can_pick_any_row_of_the_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_keys(monkeypatch, baidu="k")
    _use(monkeypatch, template(excel_name="a.xlsx"))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲公司"], ["乙公司"]]))
    ask = {"content": "@【名称】", "model_id": "baidu-deepseek-v3.2", "prompt_id": PROMPT_ID}
    _, prompt = await asking.prepare_trial(FakeSession(), FULL_ACCESS, row=1, **ask)  # type: ignore[arg-type]
    assert prompt == "乙公司"
    with pytest.raises(ApiError, match="只有 2 行，没有第 3 行"):
        await asking.prepare_trial(FakeSession(), FULL_ACCESS, row=2, **ask)  # type: ignore[arg-type]


async def test_trial_answer_is_parsed_by_the_output_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """试发答完按输出字段解析，和批量任务同一套规则：页面不用自己猜这一行能不能解析。"""

    _with_keys(monkeypatch, ark="k")
    model, message = await asking.prepare_chat(FakeSession(), "deepseek-v4-flash", "问")
    answers = {
        '[{"行业": "制造"}]': 'data: {"parsed": [{"行业": "制造"}]}\n\n',
        "说不清": 'data: {"parsed": null}\n\n',
    }
    for text, parsed in answers.items():
        monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": text}]))
        chunks = [chunk async for chunk in asking.stream_answer(model, message, thinking=False, trial_fields=["行业"])]
        assert chunks[-2:] == [parsed, "data: [DONE]\n\n"]
    # 出错的回答没有解析的意义；对话不传输出字段，也不解析。
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": "半"}, {"error": "超时"}]))
    chunks = [chunk async for chunk in asking.stream_answer(model, message, thinking=False, trial_fields=["行业"])]
    assert not any('"parsed"' in chunk for chunk in chunks)
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": '[{"行业": "制造"}]'}]))
    chunks = [chunk async for chunk in asking.stream_answer(model, message, thinking=False)]
    assert not any('"parsed"' in chunk or '"prompt"' in chunk for chunk in chunks)


async def test_test_rows_give_the_head_of_each_cell_and_its_length(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, template(excel_name="a.xlsx", excel_rows=2))
    storage.write_atomic(
        storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称", "正文"], ["甲", "长" * 500], ["乙", ""]])
    )
    data = await test_rows.preview(FakeSession(), FULL_ACCESS, PROMPT_ID)  # type: ignore[arg-type]
    assert (data["headers"], data["total"]) == (["名称", "正文"], 2)
    first, second = data["rows"]
    assert (first["row"], first["values"]["正文"], first["lengths"]["正文"]) == (1, "长" * 200, 500)
    assert second["values"] == {"名称": "乙", "正文": ""}
    _use(monkeypatch, template(excel_name=""))
    assert await test_rows.preview(FakeSession(), FULL_ACCESS, PROMPT_ID) == {"headers": [], "total": 0, "rows": []}  # type: ignore[arg-type]


async def test_trial_uses_the_code_table_chosen_on_the_page_even_before_saving(monkeypatch: pytest.MonkeyPatch) -> None:
    """改了码表没保存就试发：右栏写着「码表全文整份放进去」，原来后端按存着的设置换成空串。"""

    _with_keys(monkeypatch, baidu="k")
    _use(monkeypatch, template(content="问：@【上传码表】", code_table="", excel_name="a.xlsx"))
    storage.write_atomic(storage.prompt_file(PROMPT_ID, "excel"), xlsx([["名称"], ["甲公司"]]))
    fetched: list[str] = []

    async def fetch(name: str) -> str:
        fetched.append(name)
        return "政策类型码表全文"

    monkeypatch.setattr(service, "fetch_code_table", fetch)
    ask = {"content": "问：@【上传码表】", "model_id": "baidu-deepseek-v3.2", "prompt_id": PROMPT_ID}
    _, prompt = await asking.prepare_trial(FakeSession(), FULL_ACCESS, code_table="policy_types", **ask)  # type: ignore[arg-type]
    assert prompt == "问：政策类型码表全文" and fetched == ["policy_types"]
    _, prompt = await asking.prepare_trial(FakeSession(), FULL_ACCESS, **ask)  # type: ignore[arg-type]
    assert prompt == "问："  # 不传就按模板存的（没选码表），替换成空
