from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.internal_calls import internal_headers

from app.application import code_tables
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.main import app
from app.repositories import code_tables as repo


async def _db() -> AsyncIterator[object]:
    yield object()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def types(_session: Any) -> list[tuple[str, ...]]:
        return [("信息化建设类", "数字政府、\n智慧城市\t等", "P0"), ("工业制造类", "", "P1")]

    monkeypatch.setattr(repo, "policy_types", types)
    monkeypatch.setitem(
        code_tables.CODE_TABLES,
        "policy_types",
        code_tables.CODE_TABLES["policy_types"].__class__(
            "政策类型", ("政策类型名称", "政策类型定义", "优先级"), types
        ),
    )
    settings = get_settings().model_copy(update={"internal_caller_secrets": {"ai-service": "s3cret"}})
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_code_table_is_tab_text_with_header_and_flattened_cells(client: TestClient) -> None:
    response = client.get("/internal/v1/code-tables/policy_types", headers=internal_headers("ai-service", "s3cret"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["title"], data["rows"]) == ("政策类型", 2)
    # 定义里的换行和制表符压成空格，否则一条类型会被模型读成好几行。
    assert data["text"].split("\n") == [
        "政策类型名称\t政策类型定义\t优先级",
        "信息化建设类\t数字政府、 智慧城市 等\tP0",
        "工业制造类\t\tP1",
    ]


def test_code_table_rejects_unknown_callers_and_names(client: TestClient) -> None:
    path = "/internal/v1/code-tables/policy_types"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=internal_headers("ai-service", "wrong!")).status_code == 401
    assert client.get(path, headers=internal_headers("policy-service", "s3cret")).status_code == 401
    missing = client.get("/internal/v1/code-tables/nope", headers=internal_headers("ai-service", "s3cret"))
    assert missing.status_code == 404


def test_every_ai_code_table_is_declared() -> None:
    assert set(code_tables.CODE_TABLES) == {"policy_types", "scenarios", "scenario_l1"}
    assert isinstance(get_settings(), Settings)
