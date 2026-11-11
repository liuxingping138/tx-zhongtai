from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.route_audit import iter_api_routes

from app.api.security import get_category_access
from app.application import asking, batch_runs, batch_start, billing, prompts, sample_runs
from app.application import test_rows as test_rows_service
from app.core import storage
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.categories import FULL_ACCESS
from app.main import app
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as prompt_repo
from tests.helpers import ACTOR, PROMPT_ID, RUN_ID, FakeSession, fake_stream, noop, template, xlsx


async def _db() -> Any:
    yield FakeSession()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_db_session] = _db
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"_", "actor"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR
    app.dependency_overrides[get_category_access] = lambda: FULL_ACCESS
    monkeypatch.setattr(prompts, "audit_template", noop)
    monkeypatch.setattr(get_settings(), "baidu_api_key", "k")
    yield TestClient(app)
    app.dependency_overrides.clear()


def _returns(module: Any, name: str, value: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(*_: Any, **__: Any) -> Any:
        return value

    monkeypatch.setattr(module, name, fake)


def test_prompt_list_includes_models(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "list_all", [template()], monkeypatch)
    body = client.get("/api/v1/ai/prompts").json()["data"]
    assert body["items"][0]["id"] == PROMPT_ID
    assert {item["id"] for item in body["models"]} >= {"deepseek-v4-flash", "baidu-deepseek-v3.2"}


def test_upload_parses_multipart_after_auth(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "get", template(), monkeypatch)
    files = {"file": ("企业.xlsx", xlsx([["名称"], ["甲"]]), "application/octet-stream")}
    response = client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/files/excel", files=files)
    assert response.status_code == 200
    assert response.json()["data"]["excel_rows"] == 1
    assert client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/files/pdf", files=files).status_code == 422
    assert client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/files/excel", data={"x": "1"}).status_code == 422


def test_download_sets_utf8_filename(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = storage.run_file(RUN_ID, "raw")
    storage.write_atomic(raw, b"a,b")

    async def download(*_: Any) -> tuple[Any, str]:
        return raw, "企业-原始返回.csv"

    monkeypatch.setattr(batch_runs, "download", download)
    response = client.get(f"/api/v1/ai/batch-runs/{RUN_ID}/files/raw")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert response.content == b"a,b"
    assert client.get(f"/api/v1/ai/batch-runs/{RUN_ID}/files/other").status_code == 422


def test_trial_streams_server_sent_events(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": "你好"}]))
    response = client.post("/api/v1/ai/stream/ask", json={"content": "hi", "model_id": "baidu-deepseek-v3.2"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert 'data: {"text": "你好"}' in response.text and response.text.endswith("data: [DONE]\n\n")


def test_invalid_requests_fail_before_streaming(client: TestClient) -> None:
    bad_model = client.post("/api/v1/ai/stream/ask", json={"content": "hi", "model_id": "nope"})
    assert bad_model.status_code == 422 and "未知模型" in bad_model.json()["message"]
    empty = client.post("/api/v1/ai/stream/ask", json={"content": " ", "model_id": "baidu-deepseek-v3.2"})
    assert empty.status_code == 422


def test_batch_routes_delegate_to_application(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def stub(name: str, value: Any) -> None:
        async def fake(*_: Any, **__: Any) -> Any:
            calls.append(name)
            return value

        monkeypatch.setattr(batch_start if name == "start_run" else batch_runs, name, fake)

    stub("list_runs", {"items": [], "total": 0})
    stub("filter_options", {"prompt_title": [], "created_by_name": []})
    stub("start_run", {"id": RUN_ID})
    stub("get_run", {"id": RUN_ID})
    stub("stop_run", {"id": RUN_ID})
    stub("retry_run", {"id": RUN_ID})
    stub("delete_run", None)
    _returns(prompt_repo, "list_all", [], monkeypatch)
    assert client.get("/api/v1/ai/batch-runs?page=2").status_code == 200
    filtered = client.get(
        "/api/v1/ai/batch-runs", params=[("run_mode", "test"), ("prompt_title", "甲"), ("prompt_title", "乙")]
    )
    assert filtered.status_code == 200
    assert client.get("/api/v1/ai/batch-runs", params={"run_mode": "half"}).status_code == 422
    assert client.get("/api/v1/ai/batch-runs/options").json()["data"]["templates"] == []
    assert client.get("/api/v1/ai/batch-runs/filter-options").status_code == 200
    assert (
        client.post(
            "/api/v1/ai/batch-runs",
            params={"prompt_id": PROMPT_ID, "limit": 10},
            files={"file": ("本次.xlsx", xlsx([["名称"], ["甲"]]))},
        ).status_code
        == 201
    )
    assert client.post("/api/v1/ai/batch-runs", params={"prompt_id": PROMPT_ID, "limit": -1}).status_code == 422
    assert client.get(f"/api/v1/ai/batch-runs/{RUN_ID}").status_code == 200
    assert client.post(f"/api/v1/ai/batch-runs/{RUN_ID}/stop").status_code == 200
    assert client.post(f"/api/v1/ai/batch-runs/{RUN_ID}/retry").status_code == 200
    assert client.delete(f"/api/v1/ai/batch-runs/{RUN_ID}").status_code == 200
    assert calls == [
        "list_runs",
        "list_runs",
        "filter_options",
        "start_run",
        "get_run",
        "stop_run",
        "retry_run",
        "delete_run",
    ]


def test_prompt_write_routes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "get", template(), monkeypatch)
    monkeypatch.setattr(prompt_repo, "delete", noop)
    _returns(run_repo, "active_for_prompt", None, monkeypatch)
    _returns(run_repo, "sample_runs_for_prompt", [], monkeypatch)
    created = client.post("/api/v1/ai/prompts", json={"title": "t", "category": "policy", "content": "c"})
    assert created.status_code == 201
    updated = client.put(
        f"/api/v1/ai/prompts/{PROMPT_ID}", json={"title": "t2", "category": "policy", "content": "c", "version": 1}
    )
    assert updated.json()["data"]["version"] == 2
    assert client.delete(f"/api/v1/ai/prompts/{PROMPT_ID}/files/code").status_code == 200
    assert client.get(f"/api/v1/ai/prompts/{PROMPT_ID}/files/code").status_code == 404
    assert client.delete(f"/api/v1/ai/prompts/{PROMPT_ID}").status_code == 200


def test_trial_hands_its_usage_to_billing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[tuple[str, str, dict[str, int], str]] = []

    async def record(kind: str, model: Any, tally: billing.CallTally, actor: Any, *, category: str) -> None:
        recorded.append((kind, model.id, tally.usage, category))

    usage = {"input_tokens": 12, "output_tokens": 3}
    monkeypatch.setattr(billing, "record_call", record)
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": "你好"}, {"usage": usage}]))
    body = {"content": "问", "model_id": "baidu-deepseek-v3.2", "category": "tender"}
    trial = client.post("/api/v1/ai/stream/ask", json=body)
    assert trial.text.endswith("data: [DONE]\n\n")
    # 还没保存的新模板：记在编辑页上选的类型下，费用账单据此归到一级业务板块。
    assert recorded == [("trial", "baidu-deepseek-v3.2", usage, "tender")]


def test_billing_route_needs_both_dates(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def daily(_session: Any, date_from: date, date_to: date) -> dict[str, Any]:
        return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "items": []}

    monkeypatch.setattr(billing, "daily", daily)
    ok = client.get("/api/v1/ai/billing", params={"date_from": "2026-10-01", "date_to": "2026-10-22"})
    assert ok.status_code == 200 and ok.json()["data"]["date_to"] == "2026-10-22"
    assert client.get("/api/v1/ai/billing", params={"date_from": "2026-10-01"}).status_code == 422


def test_test_data_route_validates_and_saves(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    async def save(_s: Any, _a: Any, _acc: Any, prompt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        seen.append(data)
        return {"id": prompt_id}

    monkeypatch.setattr(prompts, "save_test_rows", save)
    body = {"file_name": "数据库样本-政策解读-1条.xlsx", "headers": ["政策正文"], "rows": [["正文"]]}
    assert client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/test-data", json=body).status_code == 200
    assert seen == [body]
    bad = client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/test-data", json={**body, "file_name": "a.csv"})
    assert bad.status_code == 422
    assert client.post(f"/api/v1/ai/prompts/{PROMPT_ID}/test-data", json={**body, "rows": []}).status_code == 422


def test_batch_file_routes_read_the_upload_after_auth(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, ...]] = []

    async def preview(
        _session: Any, _access: Any, prompt_id: str, upload: tuple[str, bytes], *, version: str
    ) -> dict[str, Any]:
        seen.append(("preview", prompt_id, upload[0], version))
        return {"name": upload[0], "rows": 2}

    async def start(_session: Any, _actor: Any, _access: Any, values: dict[str, Any], *, upload: Any) -> Any:
        seen.append(("start", values["limit"], values["thinking"], upload[0], values["version"]))
        return {"id": RUN_ID}

    async def rows(_session: Any, _access: Any, run_id: str, *, failed_only: bool) -> dict[str, Any]:
        seen.append(("rows", run_id, failed_only))
        return {"items": []}

    async def blank(_session: Any, _access: Any, prompt_id: str, *, version: str) -> tuple[bytes, str]:
        seen.append(("template", prompt_id, version))
        return b"xlsx", "企业行业-第3版数据模板.xlsx"

    monkeypatch.setattr(batch_start, "preview_input", preview)
    monkeypatch.setattr(batch_start, "start_run", start)
    monkeypatch.setattr(batch_runs, "run_rows", rows)
    monkeypatch.setattr(batch_start, "input_template", blank)
    files = {"file": ("本次数据.xlsx", xlsx([["名称"], ["甲"], ["乙"]]))}
    params = {"prompt_id": PROMPT_ID}
    # 下载数据模板不能被 /{run_id} 当成查任务。
    template_file = client.get("/api/v1/ai/batch-runs/input-template", params=params)
    assert template_file.status_code == 200 and template_file.content == b"xlsx"
    draft = {**params, "version": "draft"}
    assert client.post("/api/v1/ai/batch-runs/input-preview", params=draft, files=files).status_code == 200
    started = client.post("/api/v1/ai/batch-runs", params={**params, "limit": 5, "thinking": True}, files=files)
    assert started.status_code == 201
    wrong = client.post("/api/v1/ai/batch-runs", params={**params, "version": "latest"}, files=files)
    assert wrong.status_code == 422
    missing = client.post("/api/v1/ai/batch-runs", params=params)
    assert missing.status_code == 422 and "数据文件" in missing.json()["message"]
    assert client.get(f"/api/v1/ai/batch-runs/{RUN_ID}/rows", params={"failed_only": True}).status_code == 200
    # 样本试跑不进批量任务列表：来源只能筛页面发起和定时任务。
    assert client.get("/api/v1/ai/batch-runs", params={"source": "sample"}).status_code == 422
    assert seen == [
        ("template", PROMPT_ID, "release"),
        ("preview", PROMPT_ID, "本次数据.xlsx", "draft"),
        ("start", 5, True, "本次数据.xlsx", "release"),
        ("rows", RUN_ID, True),
    ]


def test_sample_run_routes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []

    async def start(_s: Any, _actor: Any, _access: Any, prompt_id: str, values: dict[str, Any]) -> Any:
        calls.append(("start", prompt_id, values["limit"]))
        return {"run": {"id": RUN_ID}, "rows": None}

    async def view(_s: Any, _access: Any, prompt_id: str, *, run_id: Any, compare_id: Any) -> Any:
        calls.append(("view", prompt_id, run_id, compare_id))
        return {"run": None, "rows": None}

    async def retry(_s: Any, _actor: Any, _access: Any, prompt_id: str, run_id: str) -> Any:
        calls.append(("retry", prompt_id, run_id))
        return {"run": None, "rows": None}

    async def test_rows(_s: Any, _access: Any, prompt_id: str) -> Any:
        calls.append(("test-rows", prompt_id))
        return {"headers": [], "total": 0, "rows": []}

    async def stop(_s: Any, _actor: Any, _access: Any, prompt_id: str) -> Any:
        calls.append(("stop", prompt_id))
        return {"run": None, "rows": None}

    monkeypatch.setattr(sample_runs, "start", start)
    monkeypatch.setattr(sample_runs, "view", view)
    monkeypatch.setattr(sample_runs, "retry", retry)
    monkeypatch.setattr(test_rows_service, "preview", test_rows)

    async def download(_s: Any, _actor: Any, _access: Any, prompt_id: str, run_id: str, kind: str) -> Any:
        calls.append(("download", prompt_id, run_id, kind))
        path = storage.run_file(run_id, kind)
        storage.write_atomic(path, b"xlsx")
        return path, "企业行业-样本试跑结果.xlsx"

    monkeypatch.setattr(sample_runs, "stop", stop)
    monkeypatch.setattr(sample_runs, "download", download)
    url = f"/api/v1/ai/prompts/{PROMPT_ID}/sample-run"
    assert client.post(url, json={"limit": 5}).status_code == 201
    assert client.post(url, json={"limit": 51}).status_code == 422
    assert client.get(url).status_code == 200
    assert client.get(url, params={"run_id": RUN_ID, "compare_id": "none"}).status_code == 200
    assert client.post(f"{url}/stop").status_code == 200
    assert client.post(f"{url}/{RUN_ID}/retry").status_code == 200
    assert client.get(f"/api/v1/ai/prompts/{PROMPT_ID}/test-rows").status_code == 200
    assert client.get(f"{url}/{RUN_ID}/files/result").content == b"xlsx"
    assert client.get(f"{url}/{RUN_ID}/files/source").status_code == 422
    assert calls == [
        ("start", PROMPT_ID, 5),
        ("view", PROMPT_ID, None, None),
        ("view", PROMPT_ID, RUN_ID, "none"),
        ("stop", PROMPT_ID),
        ("retry", PROMPT_ID, RUN_ID),
        ("test-rows", PROMPT_ID),
        ("download", PROMPT_ID, RUN_ID, "result"),
    ]


def test_downloading_a_growing_file_sends_the_length_seen_at_the_start(tmp_path: Path) -> None:
    """运行中的任务每答一行都往原始返回里追加：读到文件尾会比声明的 Content-Length 多，下载被掐断。"""

    import asyncio

    from app.api.schemas import path_response

    raw = tmp_path / "temp.csv"
    raw.write_bytes(b"a" * 10)
    response = path_response(raw, "原始返回.csv")
    raw.write_bytes(b"a" * 25)  # 开始发之前 worker 又写了几行

    async def body() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[misc]

    assert response.headers["content-length"] == "10"
    assert asyncio.run(body()) == b"a" * 10
