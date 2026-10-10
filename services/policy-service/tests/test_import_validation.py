"""信源、基础标签的 Excel 导入：任一行不通过就整批退回，全部通过才写入。不连数据库，仓储和会话用替身。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.policy.application import base_tags, importing, sources
from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, Source

ACTOR = SimpleNamespace(id="u1", name="测试")


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)


def _source(**values: str) -> dict[str, str]:
    row = {"site_name": "某网站", "province_name": "北京市", "city_name": "北京市", "tag": "政策", "url": ""}
    return row | values


@pytest.fixture
def source_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    env: dict[str, Any] = {"rows": [], "internal_ids": set(), "site_codes": set(), "marked": None}

    async def parse(_content: bytes, _columns: object, *, subject: str) -> list[dict[str, str]]:
        return env["rows"]

    async def encode(_columns: object, marked: list[dict[str, str]]) -> bytes:
        env["marked"] = marked
        return b"skipped"

    monkeypatch.setattr(sources, "parse_sheet_async", parse)
    monkeypatch.setattr(importing, "encode_skipped_file_async", encode)
    monkeypatch.setattr(sources, "enqueue_event", AsyncMock())
    monkeypatch.setattr(sources.repo, "list_internal_ids", AsyncMock(side_effect=lambda _s: env["internal_ids"]))
    monkeypatch.setattr(sources.repo, "list_site_codes", AsyncMock(side_effect=lambda _s: env["site_codes"]))
    return env


def _reasons(env: dict[str, Any]) -> list[str]:
    return [row["skip_reason"] for row in env["marked"]]


class TestImportSources:
    async def test_all_valid_rows_are_inserted_with_allocated_site_codes(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [
            _source(site_name="甲", district_code="110101"),
            _source(site_name="乙", district_code="110101"),
            _source(site_name="丙", site_code="11010200009"),
        ]
        source_env["site_codes"] = {"11010100003"}
        session = _Session()
        result = await sources.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["inserted"] == 3
        assert result["skipped_file"] is None
        added: list[Source] = session.added
        # 同区县在库里最大序号之后顺延；自带编码的行原样保留。
        assert [row.site_code for row in added] == ["11010100004", "11010100005", "11010200009"]
        assert all(row.created_by_name == "测试" for row in added)

    async def test_one_bad_row_rejects_the_whole_file(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_name="甲", district_code="110101"), _source(site_name="")]
        session = _Session()
        result = await sources.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["rejected"] is True
        assert (result["inserted"], result["skipped"], result["total"]) == (0, 1, 2)
        assert session.added == []
        assert _reasons(source_env)[0] == "通过"
        assert "网站名称为空" in _reasons(source_env)[1]

    async def test_missing_area_code_prefers_the_reason_carried_in_the_file(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_name="甲", skip_reason="区县不标准"), _source(site_name="乙")]
        await sources.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

        assert _reasons(source_env) == ["区县不标准", "省市区编码为空"]

    async def test_given_site_code_makes_area_code_optional(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_code="11010100001")]
        result = await sources.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

        assert result["inserted"] == 1

    async def test_site_code_and_internal_id_conflicts_are_reported(self, source_env: dict[str, Any]) -> None:
        dup = _source(site_name="重复", district_code="110101")
        source_env["rows"] = [
            _source(site_name="甲", site_code="11010A"),
            _source(site_name="乙", site_code="11010100001"),
            _source(site_name="丙", site_code="11010100002"),
            _source(site_name="丁", site_code="11010100002"),
            dup,
            dict(dup),
            _source(site_name="已有", district_code="110101"),
        ]
        source_env["site_codes"] = {"11010100001"}
        source_env["internal_ids"] = {sources.make_internal_id("已有", "北京市", "北京市", "政策")}
        await sources.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

        reasons = _reasons(source_env)
        assert reasons[0] == "网站编码不合法"
        assert reasons[1] == "网站编码已存在"
        assert reasons[2] == reasons[3] == "文件内网站编码重复"
        assert reasons[4] == reasons[5] == "网站名称+省份+地市+标签重复"
        assert reasons[6] == "内部唯一id已存在"


@pytest.fixture
def tag_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    env: dict[str, Any] = {"rows": [], "hashes": set(), "marked": None}

    async def parse(_content: bytes, _columns: object, *, subject: str) -> list[dict[str, str]]:
        return env["rows"]

    async def encode(_columns: object, marked: list[dict[str, str]]) -> bytes:
        env["marked"] = marked
        return b"skipped"

    monkeypatch.setattr(base_tags, "parse_sheet_async", parse)
    monkeypatch.setattr(importing, "encode_skipped_file_async", encode)
    monkeypatch.setattr(base_tags, "enqueue_event", AsyncMock())
    monkeypatch.setattr(base_tags.repo, "list_hashes", AsyncMock(side_effect=lambda _s: env["hashes"]))
    return env


def _tag(**values: str) -> dict[str, str]:
    return {"policy_name": "某政策", "province_code": "11"} | values


class TestImportBaseTags:
    async def test_valid_rows_are_inserted_with_content_hash(self, tag_env: dict[str, Any]) -> None:
        tag_env["rows"] = [_tag(policy_name="甲"), _tag(policy_name="乙")]
        session = _Session()
        result = await base_tags.import_base_tags(session, ACTOR, b"")  # type: ignore[arg-type]

        added: list[BaseTag] = session.added
        assert result["inserted"] == 2
        assert [row.policy_name for row in added] == ["甲", "乙"]
        assert added[0].content_hash == base_tags.content_hash(
            base_tags._values(_tag(policy_name="甲")), BASE_TAG_FIELDS
        )

    async def test_any_bad_row_rejects_the_file_with_reasons(self, tag_env: dict[str, Any]) -> None:
        existing = _tag(policy_name="已有")
        tag_env["hashes"] = {base_tags.content_hash(base_tags._values(existing), BASE_TAG_FIELDS)}
        tag_env["rows"] = [
            _tag(policy_name="甲"),
            _tag(policy_name=""),
            _tag(policy_name="无编码", province_code="", skip_reason="地市不标准"),
            existing,
            _tag(policy_name="双份"),
            _tag(policy_name="双份"),
        ]
        session = _Session()
        result = await base_tags.import_base_tags(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["rejected"] is True
        assert (result["skipped"], result["total"]) == (5, 6)
        assert session.added == []
        reasons = [row["skip_reason"] for row in tag_env["marked"]]
        assert reasons[:4] == ["通过", "政策名称为空", "地市不标准", "内容已存在"]
        assert reasons[4] == reasons[5] == "文件内内容重复"
