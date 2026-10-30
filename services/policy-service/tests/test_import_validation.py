"""信源、基础标签的 Excel 导入：任一行不通过就整批退回，全部通过才写入。不连数据库，仓储和会话用替身。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.policy.application import base_tags, importing, source_import, sources
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
    env: dict[str, Any] = {"rows": [], "internal_ids": set(), "sites": {}, "marked": None}

    async def parse(_content: bytes, _columns: object, *, subject: str) -> list[dict[str, str]]:
        return env["rows"]

    async def encode(_columns: object, marked: list[dict[str, str]]) -> bytes:
        env["marked"] = marked
        return b"skipped"

    monkeypatch.setattr(source_import, "parse_sheet_async", parse)
    monkeypatch.setattr(importing, "encode_skipped_file_async", encode)
    monkeypatch.setattr(source_import, "enqueue_event", AsyncMock())
    monkeypatch.setattr(sources.repo, "list_internal_ids", AsyncMock(side_effect=lambda _s: env["internal_ids"]))
    monkeypatch.setattr(sources.repo, "site_identities", AsyncMock(side_effect=lambda _s: env["sites"]))
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
        source_env["sites"] = {"11010100003": {("别的网站", "北京市", "北京市")}}
        session = _Session()
        result = await source_import.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["inserted"] == 3
        assert result["skipped_file"] is None
        added: list[Source] = session.added
        # 同区县在库里最大序号之后顺延；自带编码的行原样保留。
        assert [row.site_code for row in added] == ["11010100004", "11010100005", "11010200009"]
        assert all(row.created_by_name == "测试" for row in added)

    async def test_column_rows_of_one_site_share_its_site_code(self, source_env: dict[str, Any]) -> None:
        """按栏目展开后同一网站几行共用一个网站编码：导出再导入、给已有网站补一个栏目行都要能导进来。"""

        source_env["rows"] = [
            _source(site_name="某局", tag="政策文件", site_code="11010100001"),
            _source(site_name="某局", tag="通知公告", site_code="11010100001"),
            _source(site_name="已有网站", tag="新栏目", site_code="11010100002"),
        ]
        source_env["sites"] = {"11010100002": {("已有网站", "北京市", "北京市")}}
        session = _Session()
        result = await source_import.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["inserted"] == 3
        assert [row.site_code for row in session.added] == ["11010100001", "11010100001", "11010100002"]

    async def test_one_bad_row_rejects_the_whole_file(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_name="甲", district_code="110101"), _source(site_name="")]
        session = _Session()
        result = await source_import.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]

        assert result["rejected"] is True
        assert (result["inserted"], result["skipped"], result["total"]) == (0, 1, 2)
        assert session.added == []
        assert _reasons(source_env)[0] == "通过"
        assert "网站名称为空" in _reasons(source_env)[1]

    async def test_online_date_from_excel_is_normalized(self, source_env: dict[str, Any]) -> None:
        # Excel 日期单元格读出来带 00:00:00。
        source_env["rows"] = [_source(site_name="甲", district_code="110101", online_date="2024-03-05 00:00:00")]
        session = _Session()
        await source_import.import_sources(session, ACTOR, b"")  # type: ignore[arg-type]
        assert session.added[0].online_date == "2024-03-05"

        source_env["rows"] = [_source(site_name="乙", district_code="110101", online_date="去年")]
        result = await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]
        assert result["rejected"] is True
        assert "上线时间格式不对" in _reasons(source_env)[0]

    async def test_overlong_cells_and_unknown_crawler_status_are_reported_not_500(
        self, source_env: dict[str, Any]
    ) -> None:
        """超长值撞到库里是 DataError，用户只看到「服务器内部错误」；爬虫状态乱写会让配置统计的合计对不上。
        都在校验说明里写明。"""

        source_env["rows"] = [
            _source(site_name="甲" * 256, district_code="110101"),
            _source(site_name="乙", district_code="110101", crawler_status="已上线"),
        ]
        result = await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]
        assert result["rejected"] is True
        reasons = _reasons(source_env)
        assert "网站名称超过 255 字" in reasons[0]
        assert "爬虫状态只能填 已爬、未爬、异常" in reasons[1]

    async def test_missing_area_code_prefers_the_reason_carried_in_the_file(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_name="甲", skip_reason="区县不标准"), _source(site_name="乙")]
        await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

        assert _reasons(source_env) == ["区县不标准", "省市区编码为空"]

    async def test_area_codes_that_cannot_make_a_site_code_prefix_are_rejected(
        self, source_env: dict[str, Any]
    ) -> None:
        """「北京」、1 位数字分不出网站编码前缀：原来分到 000000 下，新建时还按空前缀锁整张信源表。"""

        source_env["rows"] = [_source(site_name="甲", province_code="北京"), _source(site_name="乙", province_code="1")]
        result = await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]
        assert result["rejected"] is True
        assert _reasons(source_env) == [sources.NON_NUMERIC_AREA_CODE] * 2
        with pytest.raises(sources.ApiError, match="省至少 2 位"):
            await sources.create_source(_Session(), ACTOR, _source(site_name="丙", province_code="北京"))  # type: ignore[arg-type]

    async def test_given_site_code_makes_area_code_optional(self, source_env: dict[str, Any]) -> None:
        source_env["rows"] = [_source(site_code="11010100001")]
        result = await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

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
        source_env["sites"] = {"11010100001": {("别的网站", "北京市", "北京市")}}
        source_env["internal_ids"] = {sources.make_internal_id("已有", "北京市", "北京市", "政策")}
        await source_import.import_sources(_Session(), ACTOR, b"")  # type: ignore[arg-type]

        reasons = _reasons(source_env)
        assert reasons[0] == "网站编码不合法"
        assert reasons[1] == "网站编码已被另一个网站使用"
        assert reasons[2] == reasons[3] == "文件内同一个网站编码对应了不同网站"
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
    monkeypatch.setattr(
        base_tags.repo, "existing_hashes", AsyncMock(side_effect=lambda _s, digests: env["hashes"] & set(digests))
    )
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
