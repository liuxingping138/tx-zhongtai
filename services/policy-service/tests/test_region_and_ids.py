from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from platform_common.columns import header_to_field
from platform_common.excel import parse_sheet

from app.policy.application.region import (
    make_internal_id,
    make_policy_uid,
    make_relation_key,
    next_site_code,
    normalize_region,
)
from app.policy.domain.fields import BASE_TAG_COLUMNS, INTERPRETATION_COLUMNS, SOURCE_COLUMNS


def test_normalize_district_misplaced_in_city() -> None:
    province, city, district = normalize_region("11", "110101", "")
    assert (province, city, district) == ("11", "1101", "110101")


def test_normalize_province_only() -> None:
    province, city, district = normalize_region("11", "", "")
    assert (province, city, district) == ("11", "1100", "110000")


def test_normalize_empty_does_not_fabricate_00() -> None:
    assert normalize_region("", "", "") == ("", "", "")


def test_normalize_city_four_digits() -> None:
    province, city, district = normalize_region("44", "4406", "")
    assert (province, city, district) == ("44", "4406", "440600")


def test_next_site_code_skips_file_reserved() -> None:
    assert next_site_code("110101", ["11010100001"]) == "11010100002"


def test_site_code_sequence() -> None:
    assert next_site_code("110000", []) == "11000000001"
    assert next_site_code("110101", ["11010100001", "11010100003"]) == "11010100004"
    assert next_site_code("110101", ["11010100099", "11010500088"]) == "11010100100"
    assert next_site_code("110101", ["11010199"]) == "11010100100"
    assert len(next_site_code("110000", ["11000000001"])) == 11


def test_internal_id_md5() -> None:
    digest = make_internal_id("北京市财政局", "北京市", "", "政务公开")
    assert digest == make_internal_id("北京市财政局", "北京市", "", "政务公开")
    assert digest != make_internal_id("北京市财政局", "北京市", "市辖区", "政务公开")
    assert len(digest) == 32


def test_interpretation_keys() -> None:
    uid = make_policy_uid("某政策")
    assert uid == make_policy_uid("某政策")
    assert make_relation_key(uid, "010000", "TO_G") == f"{uid}010000TO_G"


def test_parse_uses_first_sheet_only() -> None:
    book = Workbook()
    first = book.active
    first.title = "全部数据"
    first.append(["网站名称", "省份", "标签"])
    first.append(["财政局", "北京市", "政务公开"])
    other = book.create_sheet("网站-0430-编码")
    other.append(["网站名称", "省份", "标签"])
    other.append(["不该读到", "上海市", "新闻"])
    raw = BytesIO()
    book.save(raw)
    items = parse_sheet(raw.getvalue(), SOURCE_COLUMNS)
    assert len(items) == 1
    assert items[0]["site_name"] == "财政局"


def test_excel_headers() -> None:
    assert header_to_field(SOURCE_COLUMNS, "网站编码") == "site_code"
    assert header_to_field(SOURCE_COLUMNS, "省份编码") == "province_code"
    assert header_to_field(SOURCE_COLUMNS, "省份") == "province_name"
    assert header_to_field(SOURCE_COLUMNS, "地市编码") == "city_code"
    assert header_to_field(SOURCE_COLUMNS, "区县编码") == "district_code"
    assert header_to_field(SOURCE_COLUMNS, "网站梳理和抓取的优先级（1、省级政府门户") == "crawl_priority"
    assert header_to_field(BASE_TAG_COLUMNS, "政策类型【参照sheet2枚举值】") == "policy_types"
    assert header_to_field(INTERPRETATION_COLUMNS, "关联主键(政策ID+行业场景编码+机会类型)") == "relation_key"
    assert header_to_field(INTERPRETATION_COLUMNS, "机会类型(TO_G  TO_B)") == "opportunity_type"
