"""PATCH 只提交显式字段，不能把模型默认空字符串当成清空。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes

from app.core.database import get_db_session
from app.main import app
from app.policy.api import base_tags as base_tags_api
from app.policy.api import interpretations as interpretations_api
from app.policy.api import sources as sources_api

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
        captured["item_id"] = item_id
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


def test_source_patch_keeps_omitted_fields_out_of_payload(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch, "/api/v1/policy/sources/{item_id}", sources_api.service, "update_source"
    )
    item_id = uuid.uuid4()
    response = client.patch(f"/api/v1/policy/sources/{item_id}", json={"version": 1, "url": "https://example.invalid"})
    assert response.status_code == 200
    assert captured["data"] == {"version": 1, "url": "https://example.invalid"}


def test_source_patch_keeps_explicit_empty_string(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch, "/api/v1/policy/sources/{item_id}", sources_api.service, "update_source"
    )
    item_id = uuid.uuid4()
    response = client.patch(f"/api/v1/policy/sources/{item_id}", json={"version": 1, "department": ""})
    assert response.status_code == 200
    assert captured["data"] == {"version": 1, "department": ""}


def test_base_tag_patch_requires_version_and_omits_defaults(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch, "/api/v1/policy/base-tags/{item_id}", base_tags_api.service, "update_base_tag"
    )
    item_id = uuid.uuid4()
    missing = client.patch(f"/api/v1/policy/base-tags/{item_id}", json={"remark": "只改备注"})
    assert missing.status_code == 422
    ok = client.patch(f"/api/v1/policy/base-tags/{item_id}", json={"version": 3, "remark": "只改备注"})
    assert ok.status_code == 200
    assert captured["data"] == {"version": 3, "remark": "只改备注"}


def test_interpretation_patch_does_not_fill_empty_defaults(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch,
        "/api/v1/policy/interpretations/{item_id}",
        interpretations_api.service,
        "update_interpretation",
    )
    item_id = uuid.uuid4()
    response = client.patch(
        f"/api/v1/policy/interpretations/{item_id}",
        json={"version": 4, "policy_summary": "摘要"},
    )
    assert response.status_code == 200
    data = captured["data"]
    assert isinstance(data, dict)
    assert data == {"version": 4, "policy_summary": "摘要"}
    assert "policy_title" not in data
    assert "data_status" not in data


def test_write_schemas_accept_every_field_the_editors_send() -> None:
    """编辑抽屉按表的可写字段提交；schema 漏一个字段（extra=forbid）整次保存就 422「参数错误」。"""

    from app.policy.api.schemas import BaseTagWrite, InterpretationWrite, SourceWrite
    from app.policy.domain.models import BASE_TAG_FIELDS, INTERPRETATION_WRITE_FIELDS, SOURCE_FIELDS

    assert set(INTERPRETATION_WRITE_FIELDS) <= set(InterpretationWrite.model_fields)
    assert set(BASE_TAG_FIELDS) <= set(BaseTagWrite.model_fields)
    assert set(SOURCE_FIELDS) <= set(SourceWrite.model_fields)


def test_interpretation_patch_saves_opportunity_fields_and_remark(monkeypatch: object) -> None:
    client, captured = _client_for(
        monkeypatch, "/api/v1/policy/interpretations/{item_id}", interpretations_api.service, "update_interpretation"
    )
    item_id = uuid.uuid4()
    body = {
        "version": 2,
        "is_new_scenario": "是",
        "new_scenario_level": "三级场景",
        "adapted_products": "云视讯",
        "purchase_reason": "政务协同",
        "remark": "人工改过",
    }
    response = client.patch(f"/api/v1/policy/interpretations/{item_id}", json=body)
    assert response.status_code == 200
    assert captured["data"] == body
