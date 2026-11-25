"""模型配置：页面增改的校验与审计、停用后不能再选、批量费用按每行完成时的单价累加。"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_common.errors import ApiError, VersionConflictError
from platform_common.route_audit import iter_api_routes

from app.application import asking, batch_execute, model_configs
from app.application.batch_output import RowResult
from app.core import storage
from app.core.config import get_settings
from app.core.database import get_db_session
from app.main import app
from tests.helpers import ACTOR, RUN_ID, FakeSession, ai_model, run

_FORM: dict[str, Any] = {
    "name": "字节-DeepSeek-V4.1-Flash经济版",
    "provider": "ark",
    "endpoint": "ep-economy",
    "thinking": "enabled",
    "reasoning_effort": "low",
    "input_price": "0.0008",
    "output_price": "0.0032",
    "peak_input_price": "0.0016",
    "peak_output_price": "0.0064",
}


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def record(_session: Any, **kwargs: Any) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(model_configs, "enqueue_event", record)
    return seen


async def test_create_validates_and_fills_default_peak_hours(
    events: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ark_api_key", "ark-ready")
    out = await model_configs.create_model(FakeSession(), ACTOR, {**_FORM, "id": "deepseek-v41-flash"})  # type: ignore[arg-type]
    assert out["peak_hours"] == "09:00-12:00,14:00-18:00"
    assert out["available"] is True
    assert (out["input_price"], out["peak_output_price"], out["flex_input_price"]) == ("0.0008", "0.0064", "")
    # 审计内容要能存 JSONB：价格是文本不是 Decimal。
    assert events[0]["event_type"] == "ai.model.created" and events[0]["changes"]["input_price"] == "0.0008"
    # 业务重复回 DUPLICATE：前端按 VERSION_CONFLICT 会提示「被别人改过」，看不到「已存在」这个真正原因。
    with pytest.raises(ApiError, match="已存在") as raised:
        await model_configs.create_model(FakeSession(), ACTOR, {**_FORM, "id": "deepseek-v41-flash"})  # type: ignore[arg-type]
    assert raised.value.code == "DUPLICATE"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "带 空格"}, "模型ID"),
        ({"provider": "openai"}, "厂商"),
        ({"endpoint": " "}, "接入点"),
        ({"input_price": "abc"}, "要填数字"),
        ({"input_price": "-1"}, "0 到 1000"),
        ({"input_price": "0.0000001"}, "6 位小数"),
        ({"peak_output_price": ""}, "一起填"),
        ({"peak_hours": "9点-12点"}, "高峰时段"),
        ({"service_tier": "flex"}, "低优单价"),
        ({"reasoning_effort": "medium"}, "思考强度"),
    ],
)
async def test_create_rejects_bad_values(overrides: dict[str, Any], message: str, events: list[dict[str, Any]]) -> None:
    with pytest.raises(ApiError, match=message):
        await model_configs.create_model(FakeSession(), ACTOR, {"id": "m1", **_FORM, **overrides})  # type: ignore[arg-type]
    assert events == []


async def test_update_records_changes_and_needs_current_version(
    model_table: list[Any], events: list[dict[str, Any]]
) -> None:
    flash = model_table[0]
    form = {**model_configs.to_dict(flash), "service_tier": "auto", "version": 1}
    out = await model_configs.update_model(FakeSession(), ACTOR, flash.id, form)  # type: ignore[arg-type]
    assert out["version"] == 2 and out["service_tier"] == "auto"
    assert events[-1]["changes"] == {"service_tier": {"from": "flex", "to": "auto"}}
    with pytest.raises(VersionConflictError):
        await model_configs.update_model(FakeSession(), ACTOR, flash.id, form)  # type: ignore[arg-type]
    # 内容没变不记审计、不涨版本。
    same = await model_configs.update_model(FakeSession(), ACTOR, flash.id, {**form, "version": 2})  # type: ignore[arg-type]
    assert same["version"] == 2 and len(events) == 1


async def test_disabled_model_is_hidden_and_cannot_be_used(
    model_table: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ark_api_key", "k")
    model_table[0].enabled = False
    ids = [item["id"] for item in await asking.available_models(FakeSession())]  # type: ignore[arg-type]
    assert ids == ["baidu-deepseek-v3.2"]
    with pytest.raises(ApiError, match="已停用"):
        await asking.resolve_model(FakeSession(), "deepseek-v4-flash")  # type: ignore[arg-type]


async def test_page_shows_prices_at_this_moment(model_table: list[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ark_api_key", "k")
    info = (await asking.available_models(FakeSession()))[0]  # type: ignore[arg-type]
    # Flash 在低优档：前端估算对话费用用低优价。
    assert (info["input_price"], info["output_price"], info["price_note"]) == ("0.0015", "0.0045", "低优档")


async def _db() -> Any:
    yield FakeSession()


def test_model_routes(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
    app.dependency_overrides[get_db_session] = _db
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"_", "actor"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR
    try:
        client = TestClient(app)
        assert [item["id"] for item in client.get("/api/v1/ai/models").json()["data"]] == [
            "deepseek-v4-flash",
            "baidu-deepseek-v3.2",
        ]
        created = client.post("/api/v1/ai/models", json={**_FORM, "id": "m2"})
        assert created.status_code == 201 and created.json()["data"]["id"] == "m2"
        updated = client.put("/api/v1/ai/models/m2", json={**_FORM, "name": "改名", "version": 1})
        assert updated.status_code == 200 and updated.json()["data"]["name"] == "改名"
        assert client.put("/api/v1/ai/models/none", json={**_FORM, "version": 1}).status_code == 404
        assert client.post("/api/v1/ai/models", json={**_FORM, "id": "m3", "secret": "x"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_batch_cost_adds_each_row_at_its_own_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """分时计价的任务跨了高峰和空闲：每行按它完成时的单价算，不按任务结束时一刀切。"""

    economy = model_configs.to_model(
        ai_model(
            service_tier="",
            input_price=Decimal("0.0008"),
            output_price=Decimal("0.0032"),
            flex_input_price=None,
            flex_output_price=None,
            peak_input_price=Decimal("0.0016"),
            peak_output_price=Decimal("0.0064"),
            peak_hours="09:00-12:00,14:00-18:00",
        )
    )
    job = batch_execute.Job(run=run(), model=economy, headers=[], rows=[{}, {}], pending=deque())
    storage.run_dir(RUN_ID).mkdir(parents=True, exist_ok=True)
    busy, idle = datetime(2026, 10, 21, 2, 0, tzinfo=UTC), datetime(2026, 10, 21, 14, 0, tzinfo=UTC)
    # 每行先按此刻算费用、再写日志，各取一次时间：北京 10:00 高峰、22:00 空闲。
    moments = iter([busy, busy, idle, idle])
    monkeypatch.setattr(batch_execute, "utcnow", lambda: next(moments))
    for myid in ("a1", "a2"):
        row = RowResult(myid, "问", "答", 1000, 1000, 0, "", 0.1)
        await batch_execute._record(job, row)
    assert job.inference_cost == Decimal("0.008") + Decimal("0.004")
