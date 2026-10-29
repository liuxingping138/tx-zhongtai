"""码表三张表的新增、编辑、导入与导出规则：必填、去重、版本冲突、只记真实变化、导出超限。仓储与审计用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError, VersionConflictError

from app.application import area_codes, policy_types, scenarios
from app.domain.models import AreaCode, PolicyType, Scenario, content_hash

ACTOR = SimpleNamespace(id="u1", name="测试")
NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        row.id = row.id or uuid.uuid4()
        self.added.append(row)


def _stamp(model: type, **values: Any) -> Any:
    return model(
        id=uuid.uuid4(), version=1, created_at=NOW, created_by_name="a", updated_at=NOW, updated_by_name="a", **values
    )


def _events(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[str]:
    events: list[str] = []
    monkeypatch.setattr(module, "enqueue_event", AsyncMock(side_effect=lambda *_a, **k: events.append(k["event_type"])))
    return events


def _parsed(monkeypatch: pytest.MonkeyPatch, module: Any, rows: list[dict[str, str]]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def encode(_columns: object, skipped: list[dict[str, str]]) -> bytes:
        captured["skipped"] = skipped
        return b"skipped"

    monkeypatch.setattr(module, "parse_sheet_async", AsyncMock(return_value=rows))
    monkeypatch.setattr(module, "encode_skipped_file_async", encode)
    return captured


class TestPolicyTypes:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, by_name=None, events=_events(monkeypatch, policy_types), rows=[])
        monkeypatch.setattr(
            policy_types.repo, "get_by_name", AsyncMock(side_effect=lambda _s, name, **_: state.by_name)
        )
        monkeypatch.setattr(policy_types.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        return state

    async def test_create_requires_a_unique_name(self, env: SimpleNamespace) -> None:
        out = await policy_types.create_policy_type(
            _Session(), ACTOR, {"type_name": " 产业扶持 ", "definition": "补贴"}
        )  # type: ignore[arg-type]
        assert out["type_name"] == "产业扶持" and env.events == ["codebook.policy_type.created"]
        with pytest.raises(ApiError, match="不能为空"):
            await policy_types.create_policy_type(_Session(), ACTOR, {"type_name": " "})  # type: ignore[arg-type]
        env.by_name = object()
        with pytest.raises(ApiError, match="已存在") as err:
            await policy_types.create_policy_type(_Session(), ACTOR, {"type_name": "产业扶持"})  # type: ignore[arg-type]
        assert err.value.http_status == 409

    async def test_update_rules(self, env: SimpleNamespace) -> None:
        env.row = _stamp(PolicyType, seq_no="1", type_name="产业扶持", definition="补贴", priority="")
        with pytest.raises(NotFoundError):
            env.row, saved = None, env.row
            await policy_types.update_policy_type(_Session(), ACTOR, uuid.uuid4(), {"version": 1})  # type: ignore[arg-type]
        env.row = saved
        with pytest.raises(VersionConflictError):
            await policy_types.update_policy_type(_Session(), ACTOR, env.row.id, {"version": 4})  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="不能为空"):
            await policy_types.update_policy_type(_Session(), ACTOR, env.row.id, {"version": 1, "type_name": " "})  # type: ignore[arg-type]
        env.by_name = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="已存在"):
            await policy_types.update_policy_type(_Session(), ACTOR, env.row.id, {"version": 1, "type_name": "改名"})  # type: ignore[arg-type]
        env.by_name = None
        unchanged = await policy_types.update_policy_type(_Session(), ACTOR, env.row.id, {"version": 1})  # type: ignore[arg-type]
        assert unchanged["version"] == 1 and env.events == []
        changed = await policy_types.update_policy_type(
            _Session(), ACTOR, env.row.id, {"version": 1, "definition": "新定义"}
        )  # type: ignore[arg-type]
        assert changed["version"] == 2 and env.events == ["codebook.policy_type.updated"]

    async def test_import_inserts_updates_and_reports_the_rest(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = _stamp(PolicyType, seq_no="1", type_name="老类型", definition="旧", priority="P1")
        same = _stamp(PolicyType, seq_no="2", type_name="没变", definition="一样", priority="P2")
        reprioritized = _stamp(PolicyType, seq_no="4", type_name="改优先级", definition="d", priority="P2")
        by_name = {"老类型": existing, "没变": same, "改优先级": reprioritized}
        monkeypatch.setattr(
            policy_types.repo, "get_by_name", AsyncMock(side_effect=lambda _s, name, **_: by_name.get(name))
        )
        captured = _parsed(
            monkeypatch,
            policy_types,
            [
                {"type_name": "新类型", "seq_no": "3", "definition": "x"},
                {"type_name": "老类型", "seq_no": "1", "definition": "新"},
                {"type_name": "没变", "seq_no": "2", "definition": "一样", "priority": ""},
                {"type_name": "改优先级", "seq_no": "4", "definition": "d", "priority": "P0"},
                {"type_name": " ", "definition": "无名"},
            ],
        )
        session = _Session()
        result = await policy_types.import_policy_types(session, ACTOR, b"")  # type: ignore[arg-type]
        assert (result["inserted"], result["updated"], result["skipped"], result["total"]) == (1, 2, 2, 5)
        assert {row["skip_reason"] for row in captured["skipped"]} == {"内容无变化", "政策类型为空"}
        assert existing.version == 2 and same.version == 1 and len(session.added) == 1
        # 旧版 Excel 没有优先级列（读成空串）不清掉已填的；填了值就照常更新。
        assert (existing.priority, same.priority, reprioritized.priority) == ("P1", "P2", "P0")

    async def test_export_is_capped_before_any_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(policy_types.repo, "count_filtered", AsyncMock(return_value=10**7))
        listed = AsyncMock()
        monkeypatch.setattr(policy_types.repo, "list_filtered", listed)
        with pytest.raises(ApiError, match="超过单次导出上限") as err:
            await policy_types.export_policy_types(_Session(), ACTOR, {"keyword": ["a"]})  # type: ignore[arg-type]
        assert err.value.http_status == 422 and "筛选结果" in str(err.value.message)
        listed.assert_not_awaited()

    async def test_export_builds_a_workbook_and_audits_the_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = _events(monkeypatch, policy_types)
        monkeypatch.setattr(policy_types.repo, "count_filtered", AsyncMock(return_value=1))
        monkeypatch.setattr(
            policy_types.repo,
            "list_filtered",
            AsyncMock(return_value=[_stamp(PolicyType, seq_no="1", type_name="甲", definition="")]),
        )
        build = AsyncMock(return_value=b"xlsx")
        monkeypatch.setattr(policy_types, "build_workbook_async", build)
        assert await policy_types.export_policy_types(_Session(), ACTOR, {}) == b"xlsx"  # type: ignore[arg-type]
        assert events == ["codebook.policy_type.exported"]
        assert build.await_args.args[1][0]["type_name"] == "甲"


class TestScenarios:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, same=None, events=_events(monkeypatch, scenarios))
        monkeypatch.setattr(scenarios.repo, "get_by_hash", AsyncMock(side_effect=lambda *_: state.same))
        monkeypatch.setattr(scenarios.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        monkeypatch.setattr(scenarios.repo, "get_by_id", AsyncMock(side_effect=lambda *_: state.row))
        return state

    async def test_create_refuses_an_identical_record(self, env: SimpleNamespace) -> None:
        out = await scenarios.create_scenario(
            _Session(), ACTOR, {"industry_scenario_code": "A01", "scenario_tag": "标签"}
        )  # type: ignore[arg-type]
        assert out["industry_scenario_code"] == "A01" and env.events == ["codebook.scenario.created"]
        env.same = object()
        with pytest.raises(ApiError, match="完全相同") as err:
            await scenarios.create_scenario(_Session(), ACTOR, {"scenario_tag": "标签"})  # type: ignore[arg-type]
        assert err.value.http_status == 409

    async def test_update_rules(self, env: SimpleNamespace) -> None:
        env.row = _stamp(Scenario, industry_scenario_code="A01", scenario_tag="标签", content_hash="old")
        with pytest.raises(VersionConflictError):
            await scenarios.update_scenario(_Session(), ACTOR, env.row.id, {"version": 3})  # type: ignore[arg-type]
        env.same = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="完全相同"):
            await scenarios.update_scenario(_Session(), ACTOR, env.row.id, {"version": 1, "scenario_tag": "别的"})  # type: ignore[arg-type]
        env.same = None
        changed = await scenarios.update_scenario(_Session(), ACTOR, env.row.id, {"version": 1, "scenario_tag": "别的"})  # type: ignore[arg-type]
        assert changed["scenario_tag"] == "别的" and changed["version"] == 2
        assert env.row.content_hash != "old"
        unchanged = await scenarios.update_scenario(_Session(), ACTOR, env.row.id, {"version": 2})  # type: ignore[arg-type]
        assert unchanged["version"] == 2

    async def test_missing_records_are_not_found(self, env: SimpleNamespace) -> None:
        with pytest.raises(NotFoundError):
            await scenarios.get_scenario(_Session(), uuid.uuid4())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await scenarios.update_scenario(_Session(), ACTOR, uuid.uuid4(), {"version": 1})  # type: ignore[arg-type]

    async def test_import_skips_content_that_already_exists(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 其他字段缺省时按空串参与哈希，和页面新增保持一致。
        def full(**kw: str) -> dict[str, str]:
            return {field: kw.get(field, "") for field in scenarios.SCENARIO_FIELDS}

        known = content_hash(full(industry_scenario_code="A01", scenario_tag="旧"), scenarios.SCENARIO_FIELDS)
        # 文件里的哈希一次查完（按文件分片），不逐行查库。
        monkeypatch.setattr(
            scenarios.repo,
            "existing_hashes",
            AsyncMock(side_effect=lambda _s, digests: {digest for digest in digests if digest == known}),
        )
        captured = _parsed(
            monkeypatch,
            scenarios,
            [
                full(industry_scenario_code="A01", scenario_tag="旧"),
                full(industry_scenario_code="A02", scenario_tag="新"),
            ],
        )
        session = _Session()
        result = await scenarios.import_scenarios(session, ACTOR, b"")  # type: ignore[arg-type]
        assert (result["inserted"], result["skipped"], result["total"]) == (1, 1, 2)
        assert captured["skipped"][0]["skip_reason"] == "内容已存在"

    async def test_export_audits_the_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = _events(monkeypatch, scenarios)
        monkeypatch.setattr(scenarios.repo, "count_filtered", AsyncMock(return_value=0))
        monkeypatch.setattr(scenarios.repo, "list_filtered", AsyncMock(return_value=[]))
        monkeypatch.setattr(scenarios, "build_workbook_async", AsyncMock(return_value=b"x"))
        await scenarios.export_scenarios(_Session(), ACTOR, {})  # type: ignore[arg-type]
        assert events == ["codebook.scenario.exported"]


class TestAreaCodes:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, by_county=None, events=_events(monkeypatch, area_codes))
        monkeypatch.setattr(area_codes.repo, "get_by_county_id", AsyncMock(side_effect=lambda *_: state.by_county))
        monkeypatch.setattr(area_codes.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        monkeypatch.setattr(area_codes.repo, "get_by_id", AsyncMock(side_effect=lambda *_: state.row))
        return state

    async def test_create_requires_a_unique_county_code(self, env: SimpleNamespace) -> None:
        out = await area_codes.create_area_code(_Session(), ACTOR, {"county_id": "110101", "county_name": "东城区"})  # type: ignore[arg-type]
        assert out["county_id"] == "110101" and env.events == ["codebook.area_code.created"]
        with pytest.raises(ApiError, match="区县编码不能为空"):
            await area_codes.create_area_code(_Session(), ACTOR, {"county_id": " "})  # type: ignore[arg-type]
        env.by_county = object()
        with pytest.raises(ApiError, match="已存在"):
            await area_codes.create_area_code(_Session(), ACTOR, {"county_id": "110101"})  # type: ignore[arg-type]

    async def test_update_rules(self, env: SimpleNamespace) -> None:
        env.row = _stamp(AreaCode, county_id="110101", county_name="东城区")
        with pytest.raises(VersionConflictError):
            await area_codes.update_area_code(_Session(), ACTOR, env.row.id, {"version": 2})  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="不能为空"):
            await area_codes.update_area_code(_Session(), ACTOR, env.row.id, {"version": 1, "county_id": ""})  # type: ignore[arg-type]
        env.by_county = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="已存在"):
            await area_codes.update_area_code(_Session(), ACTOR, env.row.id, {"version": 1, "county_id": "110102"})  # type: ignore[arg-type]
        env.by_county = None
        changed = await area_codes.update_area_code(
            _Session(), ACTOR, env.row.id, {"version": 1, "alias_county_name": "东城"}
        )  # type: ignore[arg-type]
        assert changed["version"] == 2 and env.events == ["codebook.area_code.updated"]
        assert (await area_codes.update_area_code(_Session(), ACTOR, env.row.id, {"version": 2}))["version"] == 2  # type: ignore[arg-type]

    async def test_missing_record_is_not_found(self, env: SimpleNamespace) -> None:
        with pytest.raises(NotFoundError):
            await area_codes.get_area_code(_Session(), uuid.uuid4())  # type: ignore[arg-type]

    async def test_import_skips_empty_and_existing_county_codes(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            area_codes.repo,
            "existing_county_ids",
            AsyncMock(side_effect=lambda _s, ids: {cid for cid in ids if cid == "110101"}),
        )
        captured = _parsed(
            monkeypatch,
            area_codes,
            [
                {"county_id": "110101"},
                {"county_id": ""},
                {"county_id": "110102", "county_name": "西城区"},
                {"county_id": "110102", "county_name": "西城区"},  # 文件里重复的一行
                {"county_id": "110103", "county_name": "长" * 300},  # 超过列宽：原来撞库报 500
            ],
        )
        result = await area_codes.import_area_codes(_Session(), ACTOR, b"")  # type: ignore[arg-type]
        assert (result["inserted"], result["skipped"]) == (1, 4)
        reasons = [row["skip_reason"] for row in captured["skipped"]]
        assert reasons[:3] == ["区县编码已存在", "区县编码为空", "区县编码已存在"]
        assert "超过" in reasons[3]

    async def test_resolve_matches_names_against_the_whole_catalog_and_audits(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalog = [
            _stamp(
                AreaCode,
                prov_id="11",
                prov_name="北京市",
                city_id="1101",
                city_name="北京市",
                county_id="110101",
                county_name="东城区",
            )
        ]
        monkeypatch.setattr(area_codes.repo, "list_all", AsyncMock(return_value=catalog))
        monkeypatch.setattr(area_codes, "run_excel_parse", AsyncMock(return_value=(b"report", 5, 2)))
        assert await area_codes.resolve_area_codes(_Session(), ACTOR, b"") == (b"report", 5, 2)  # type: ignore[arg-type]
        assert env.events == ["codebook.area_code.resolved"]
