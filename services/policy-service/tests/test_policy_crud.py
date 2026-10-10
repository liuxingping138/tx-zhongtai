"""信源与基础标签的新增、编辑、清空：必填、重复、版本冲突、只记真实变化。仓储和审计用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError, VersionConflictError

from app.policy.application import base_tags, sources
from app.policy.domain.models import BaseTag, Source

ACTOR = SimpleNamespace(id="u1", name="测试")
NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        row.id = row.id or uuid.uuid4()
        self.added.append(row)


def _stamped(model: type, **values: Any) -> Any:
    return model(
        version=1, created_at=NOW, created_by_name="a", updated_at=NOW, updated_by_name="a", id=uuid.uuid4(), **values
    )


class TestSources:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, internal=None, site=None, existing_codes=[], events=[])
        audit = AsyncMock(side_effect=lambda *_a, **k: state.events.append(k["event_type"]))
        monkeypatch.setattr(sources, "enqueue_event", audit)
        monkeypatch.setattr(sources.repo, "get_by_internal_id", AsyncMock(side_effect=lambda *_: state.internal))
        monkeypatch.setattr(sources.repo, "get_by_site_code", AsyncMock(side_effect=lambda *_: state.site))
        monkeypatch.setattr(sources.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        monkeypatch.setattr(sources.repo, "get_by_id", AsyncMock(side_effect=lambda *_: state.row))
        monkeypatch.setattr(
            sources.repo, "list_site_codes_for_district", AsyncMock(side_effect=lambda *_: state.existing_codes)
        )
        return state

    def _data(self, **overrides: str) -> dict[str, str]:
        return {
            "site_name": "某网站",
            "province_name": "北京市",
            "city_name": "北京市",
            "tag": "政策",
            "district_code": "110101",
        } | overrides

    async def test_create_allocates_the_next_site_code_in_the_district(self, env: SimpleNamespace) -> None:
        env.existing_codes = ["11010100003"]
        session = _Session()
        out = await sources.create_source(session, ACTOR, self._data())  # type: ignore[arg-type]
        assert out["site_code"] == "11010100004" and out["version"] == 1
        assert env.events == ["policy.source.created"]

    async def test_create_requires_a_name_and_some_area_code(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="网站名称"):
            await sources.create_source(_Session(), ACTOR, self._data(site_name=" "))  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="省市区编码"):
            await sources.create_source(_Session(), ACTOR, self._data(district_code=""))  # type: ignore[arg-type]

    async def test_duplicate_identity_and_code_collision_are_conflicts(self, env: SimpleNamespace) -> None:
        env.internal = object()
        with pytest.raises(ApiError, match="内部唯一 id") as first:
            await sources.create_source(_Session(), ACTOR, self._data())  # type: ignore[arg-type]
        assert first.value.http_status == 409
        env.internal, env.site = None, object()
        with pytest.raises(ApiError, match="网站编码冲突"):
            await sources.create_source(_Session(), ACTOR, self._data())  # type: ignore[arg-type]

    def _row(self) -> Source:
        values = {
            "site_name": "某网站",
            "province_name": "北京市",
            "city_name": "北京市",
            "tag": "政策",
            "province_code": "11",
            "city_code": "1101",
            "district_code": "110101",
        }
        return _stamped(Source, internal_id="old", site_code="11010100001", **values)

    async def test_update_needs_the_current_version(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        with pytest.raises(VersionConflictError):
            await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 7})  # type: ignore[arg-type]
        env.row = None
        with pytest.raises(NotFoundError):
            await sources.update_source(_Session(), ACTOR, uuid.uuid4(), {"version": 1})  # type: ignore[arg-type]

    async def test_update_records_only_what_changed_and_bumps_the_version(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        out = await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 1, "department": "市政府"})  # type: ignore[arg-type]
        assert out["department"] == "市政府" and out["version"] == 2
        assert env.events == ["policy.source.updated"]

    async def test_update_without_changes_writes_nothing(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        env.row.internal_id = sources.make_internal_id("某网站", "北京市", "北京市", "政策")
        out = await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 1})  # type: ignore[arg-type]
        assert out["version"] == 1 and env.events == []

    async def test_renaming_into_another_records_identity_is_a_conflict(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        env.internal = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="内部唯一 id"):
            await sources.update_source(_Session(), ACTOR, env.row.id, {"version": 1, "site_name": "别的网站"})  # type: ignore[arg-type]

    async def test_get_and_purge(self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(NotFoundError):
            await sources.get_source(_Session(), uuid.uuid4())  # type: ignore[arg-type]
        monkeypatch.setattr(sources.repo, "delete_all", AsyncMock(return_value=12))
        assert await sources.purge_sources(_Session(), ACTOR) == {"deleted": 12}  # type: ignore[arg-type]
        assert env.events == ["policy.source.purged"]


class TestBaseTags:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, same=None, events=[])
        monkeypatch.setattr(
            base_tags, "enqueue_event", AsyncMock(side_effect=lambda *_a, **k: state.events.append(k["event_type"]))
        )
        monkeypatch.setattr(base_tags.repo, "get_by_hash", AsyncMock(side_effect=lambda *_: state.same))
        monkeypatch.setattr(base_tags.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        monkeypatch.setattr(base_tags.repo, "get_by_id", AsyncMock(side_effect=lambda *_: state.row))
        return state

    async def test_create_stores_a_content_hash_and_audits(self, env: SimpleNamespace) -> None:
        out = await base_tags.create_base_tag(_Session(), ACTOR, {"policy_name": "某政策", "province_code": "11"})  # type: ignore[arg-type]
        assert out["policy_name"] == "某政策" and env.events == ["policy.base_tag.created"]

    async def test_create_needs_a_name_and_refuses_identical_content(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="政策名称"):
            await base_tags.create_base_tag(_Session(), ACTOR, {"policy_name": ""})  # type: ignore[arg-type]
        env.same = object()
        with pytest.raises(ApiError, match="完全相同") as err:
            await base_tags.create_base_tag(_Session(), ACTOR, {"policy_name": "某政策"})  # type: ignore[arg-type]
        assert err.value.http_status == 409

    def _row(self) -> BaseTag:
        row = _stamped(BaseTag, policy_name="某政策", province_code="11")
        row.refresh_hash()
        return row

    async def test_update_changes_the_hash_with_the_content(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        before = env.row.content_hash
        out = await base_tags.update_base_tag(_Session(), ACTOR, env.row.id, {"version": 1, "remark": "备注"})  # type: ignore[arg-type]
        assert out["remark"] == "备注" and out["version"] == 2 and env.row.content_hash != before

    async def test_update_rules(self, env: SimpleNamespace) -> None:
        env.row = self._row()
        with pytest.raises(VersionConflictError):
            await base_tags.update_base_tag(_Session(), ACTOR, env.row.id, {"version": 5})  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="政策名称"):
            await base_tags.update_base_tag(_Session(), ACTOR, env.row.id, {"version": 1, "policy_name": " "})  # type: ignore[arg-type]
        env.same = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="完全相同"):
            await base_tags.update_base_tag(_Session(), ACTOR, env.row.id, {"version": 1, "remark": "x"})  # type: ignore[arg-type]
        env.same = None
        unchanged = await base_tags.update_base_tag(_Session(), ACTOR, env.row.id, {"version": 1})  # type: ignore[arg-type]
        assert unchanged["version"] == 1 and env.events == []

    async def test_missing_rows_are_not_found(self, env: SimpleNamespace) -> None:
        with pytest.raises(NotFoundError):
            await base_tags.get_base_tag(_Session(), uuid.uuid4())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await base_tags.update_base_tag(_Session(), ACTOR, uuid.uuid4(), {"version": 1})  # type: ignore[arg-type]
