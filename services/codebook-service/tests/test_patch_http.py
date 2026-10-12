"""PATCH 只提交显式字段，不能把模型默认空字符串当成清空。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes

from app.api import area_codes as area_codes_api
from app.api import policy_types as policy_types_api
from app.api import scenarios as scenarios_api
from app.api.schemas import ScenarioPatch
from app.core.database import get_db_session
from app.main import app

_ACTOR = Actor(id="00000000-0000-0000-0000-000000000001", name="测试")


async def _db():  # type: ignore[no-untyped-def]
    yield None


def _client_for(
    monkeypatch: object,
    route_path: str,
    module: object,
    method_name: str,
) -> tuple[TestClient, dict[str, object]]:
    captured: dict[str, object] = {}

    async def fake_update(session, actor, item_id, data):  # type: ignore[no-untyped-def]
        del session, actor
        captured["data"] = data
        return {"id": str(item_id), "version": 2}

    route = next(item for item in iter_api_routes(app) if item.path == route_path and "PATCH" in item.methods)
    app.dependency_overrides[get_db_session] = _db
    for dep in route.dependant.dependencies:
        if dep.name == "actor":
            app.dependency_overrides[dep.call] = lambda: _ACTOR
    monkeypatch.setattr(module, method_name, fake_update)  # type: ignore[attr-defined]
    return TestClient(app), captured


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_scenario_model_dump_excludes_unset_defaults() -> None:
    dumped = ScenarioPatch.model_validate({"version": 1, "scenario_tag": "changed"}).model_dump(exclude_unset=True)
    assert dumped == {"version": 1, "scenario_tag": "changed"}
    cleared = ScenarioPatch.model_validate({"version": 1, "scenario_tag": ""}).model_dump(exclude_unset=True)
    assert cleared == {"version": 1, "scenario_tag": ""}


def test_scenario_patch_http_passes_only_submitted_fields(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch, "/api/v1/codebook/scenarios/{item_id}", scenarios_api.service, "update_scenario"
    )
    item_id = uuid.uuid4()
    response = client.patch(
        f"/api/v1/codebook/scenarios/{item_id}",
        json={"version": 1, "scenario_tag": "changed"},
    )
    assert response.status_code == 200
    assert captured["data"] == {"version": 1, "scenario_tag": "changed"}


def test_policy_type_patch_http(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch,
        "/api/v1/codebook/policy-types/{item_id}",
        policy_types_api.service,
        "update_policy_type",
    )
    item_id = uuid.uuid4()
    response = client.patch(f"/api/v1/codebook/policy-types/{item_id}", json={"version": 2, "definition": "说明"})
    assert response.status_code == 200
    assert captured["data"] == {"version": 2, "definition": "说明"}


def test_area_code_patch_http(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch,
        "/api/v1/codebook/area-codes/{item_id}",
        area_codes_api.service,
        "update_area_code",
    )
    item_id = uuid.uuid4()
    response = client.patch(f"/api/v1/codebook/area-codes/{item_id}", json={"version": 5, "alias_city_name": "杭"})
    assert response.status_code == 200
    assert captured["data"] == {"version": 5, "alias_city_name": "杭"}
