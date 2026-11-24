"""批量任务「从政策库取数」两个接口：请求体校验、总字数上限、类型授权，以及超过 Excel 单元格上限的格子要提醒。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.route_audit import iter_api_routes

from app.api.security import get_category_access
from app.application import batch_start
from app.application.sheets import CELL_MAX
from app.core.database import get_db_session
from app.domain.categories import FULL_ACCESS, CategoryAccess
from app.main import app
from tests.helpers import ACTOR, PROMPT_ID, FakeSession, release
from tests.test_batch_inputs import _online

PREVIEW = "/api/v1/ai/batch-runs/from-rows/preview"
START = "/api/v1/ai/batch-runs/from-rows"


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
    _online(monkeypatch, release())
    yield TestClient(app, headers={"Authorization": "Bearer test"})
    app.dependency_overrides.clear()


def _body(rows: list[list[str]] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "prompt_id": PROMPT_ID,
        "file_name": "数据库样本-政策解读-2条.xlsx",
        "headers": ["名称", "政策正文"],
        "rows": rows if rows is not None else [["甲", "正文"], ["乙", "正文"]],
        **extra,
    }


def test_both_routes_need_the_batch_run_permission() -> None:
    routes = {route.path: route for route in iter_api_routes(app)}
    for path in (PREVIEW, START):
        marks = [getattr(dep.call, "__authz_permission__", None) for dep in routes[path].dependant.dependencies]
        assert ("ai.batch_runs", "run") in marks, path


def test_preview_checks_columns_without_creating_a_run(client: TestClient) -> None:
    reply = client.post(PREVIEW, json=_body())
    assert reply.status_code == 200, reply.text
    data = reply.json()["data"]
    assert (data["rows"], data["truncated_cells"], data["warning"]) == (2, 0, "")


def test_start_creates_a_run_from_the_rows(client: TestClient) -> None:
    reply = client.post(START, json=_body(limit=1))
    assert reply.status_code == 201, reply.text
    assert (reply.json()["data"]["total_count"], reply.json()["data"]["run_mode"]) == (1, "test")


@pytest.mark.parametrize(
    "body",
    [
        _body(file_name="样本.csv"),
        _body(rows=[]),
        _body(rows=[["甲", "x"]] * 501),
        _body(headers=[]),
        _body(version="latest"),
    ],
)
def test_malformed_requests_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post(PREVIEW, json=body).status_code == 422


def test_rows_wider_than_the_headers_are_rejected(client: TestClient) -> None:
    reply = client.post(PREVIEW, json=_body(rows=[["甲", "正文"], ["乙", "正文", "多出来的"]]))
    assert reply.status_code == 422 and "第 2 行比表头多出几列" in reply.text


def test_oversized_payloads_fail_fast_before_building_excel(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_start, "ROWS_CHARS_MAX", 10)

    def never(*_: Any) -> bytes:
        raise AssertionError("超了上限还去生成 Excel")

    monkeypatch.setattr(batch_start, "rows_workbook", never)
    for path in (PREVIEW, START):
        reply = client.post(path, json=_body(rows=[["甲", "很长很长的正文"]]))
        assert reply.status_code == 413 and "超过单次上限" in reply.text


def test_cells_over_the_excel_limit_come_with_a_warning(client: TestClient) -> None:
    reply = client.post(PREVIEW, json=_body(rows=[["甲", "字" * (CELL_MAX + 1)], ["乙", "正文"]]))
    data = reply.json()["data"]
    assert reply.status_code == 200 and data["truncated_cells"] == 1
    assert "会被截断" in data["warning"] and f"{CELL_MAX:,}" in data["warning"]


def test_templates_of_a_category_the_user_cannot_edit_are_refused(client: TestClient) -> None:
    app.dependency_overrides[get_category_access] = lambda: CategoryAccess(
        readable=frozenset({"policy"}), editable=frozenset({"customer"})
    )
    for path in (PREVIEW, START):
        assert client.post(path, json=_body()).status_code == 403
