"""列表和导出共用同一套筛选条件；未知筛选字段在仓储和接口层都要报错。"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes

from app.core.database import get_db_session
from app.knowledge.api.routes import get_knowledge_access, knowledge_filters
from app.knowledge.domain.scopes import FULL_ACCESS
from app.knowledge.repositories import knowledge as repo
from app.main import app


def _query_params(dep: Any) -> set[str]:
    return {name for name in inspect.signature(dep).parameters if name not in {"self", "args", "kwargs"}}


def test_filter_params_match_repository_filter_columns() -> None:
    params = _query_params(knowledge_filters)
    assert params == set(repo.FILTER_COLUMNS), f"筛选参数不一致：{params ^ set(repo.FILTER_COLUMNS)}"


async def test_unknown_search_option_field_raises_key_error() -> None:
    with pytest.raises(KeyError):
        await repo.search_option_values(AsyncMock(), field="non_existent_field", keyword=None)


def test_unknown_search_option_field_returns_422() -> None:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    route = next(item for item in iter_api_routes(app) if item.path == "/api/v1/thinktank/knowledge/options/search")
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_knowledge_access] = lambda: FULL_ACCESS
    for dep in route.dependant.dependencies:
        if dep.name == "_" and dep.call is not None:
            app.dependency_overrides[dep.call] = lambda: Actor(id="u1", name="测试")
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/thinktank/knowledge/options/search", params={"field": "unknown"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_full_access_includes_all_scopes() -> None:
    summary = FULL_ACCESS.to_summary()
    assert "产品" in summary["editable_file_types"]  # type: ignore[operator]
    assert "未定义" in summary["editable_file_types"]  # type: ignore[operator]
    assert "党政" in summary["editable_industries"]  # type: ignore[operator]
    assert "无" in summary["editable_industries"]  # type: ignore[operator]
