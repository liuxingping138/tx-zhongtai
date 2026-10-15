from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.route_audit import iter_api_routes

from app.application import asking, batch_runs, prompts
from app.core.config import get_settings
from app.core.database import get_db_session
from app.main import app
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
    monkeypatch.setattr(prompts, "enqueue_event", noop)
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
    async def download(*_: Any) -> tuple[bytes, str]:
        return b"a,b", "企业-原始返回.csv"

    monkeypatch.setattr(batch_runs, "download", download)
    response = client.get(f"/api/v1/ai/batch-runs/{RUN_ID}/files/raw")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert client.get(f"/api/v1/ai/batch-runs/{RUN_ID}/files/other").status_code == 422


def test_chat_streams_server_sent_events(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asking, "stream_responses", fake_stream([{"text": "你好"}]))
    response = client.post("/api/v1/ai/stream/chat", json={"message": "hi", "model_id": "baidu-deepseek-v3.2"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert 'data: {"text": "你好"}' in response.text and response.text.endswith("data: [DONE]\n\n")


def test_invalid_requests_fail_before_streaming(client: TestClient) -> None:
    bad_model = client.post("/api/v1/ai/stream/chat", json={"message": "hi", "model_id": "nope"})
    assert bad_model.status_code == 422 and "未知模型" in bad_model.json()["message"]
    empty = client.post("/api/v1/ai/stream/ask", json={"content": " ", "model_id": "baidu-deepseek-v3.2"})
    assert empty.status_code == 422


def test_batch_routes_delegate_to_application(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def stub(name: str, value: Any) -> None:
        async def fake(*_: Any, **__: Any) -> Any:
            calls.append(name)
            return value

        monkeypatch.setattr(batch_runs, name, fake)

    stub("list_runs", {"items": [], "total": 0})
    stub("start_run", {"id": RUN_ID})
    stub("get_run", {"id": RUN_ID})
    stub("stop_run", {"id": RUN_ID})
    stub("delete_run", None)
    _returns(prompt_repo, "list_all", [], monkeypatch)
    assert client.get("/api/v1/ai/batch-runs?page=2").status_code == 200
    assert client.get("/api/v1/ai/batch-runs/options").json()["data"]["templates"] == []
    assert client.post("/api/v1/ai/batch-runs", json={"prompt_id": PROMPT_ID, "limit": 10}).status_code == 201
    assert client.post("/api/v1/ai/batch-runs", json={"prompt_id": PROMPT_ID, "limit": -1}).status_code == 422
    assert client.get(f"/api/v1/ai/batch-runs/{RUN_ID}").status_code == 200
    assert client.post(f"/api/v1/ai/batch-runs/{RUN_ID}/stop").status_code == 200
    assert client.delete(f"/api/v1/ai/batch-runs/{RUN_ID}").status_code == 200
    assert calls == ["list_runs", "start_run", "get_run", "stop_run", "delete_run"]
    assert len(client.get("/api/v1/ai/chat/models").json()["data"]) == 4


def test_prompt_write_routes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _returns(prompt_repo, "get", template(), monkeypatch)
    monkeypatch.setattr(prompt_repo, "delete", noop)
    created = client.post("/api/v1/ai/prompts", json={"title": "t", "content": "c"})
    assert created.status_code == 201
    updated = client.put(f"/api/v1/ai/prompts/{PROMPT_ID}", json={"title": "t2", "content": "c", "version": 1})
    assert updated.json()["data"]["version"] == 2
    assert client.delete(f"/api/v1/ai/prompts/{PROMPT_ID}/files/code").status_code == 200
    assert client.get(f"/api/v1/ai/prompts/{PROMPT_ID}/files/code").status_code == 404
    assert client.delete(f"/api/v1/ai/prompts/{PROMPT_ID}").status_code == 200
