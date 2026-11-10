from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from platform_common.columns import header_to_field
from platform_common.excel import parse_sheet

from app.application.area_match import AreaSnap, match_area
from app.application.area_resolve import build_resolve_workbook
from app.application.area_sql import parse_area_sql
from app.domain.fields import AREA_CODE_COLUMNS, POLICY_TYPE_COLUMNS, SCENARIO_COLUMNS
from app.domain.models import SCENARIO_FIELDS, content_hash


def test_header_matches_user_excel_titles() -> None:
    assert header_to_field(POLICY_TYPE_COLUMNS, "政策类型") == "type_name"
    assert header_to_field(SCENARIO_COLUMNS, "行业场景编码") == "industry_scenario_code"
    assert header_to_field(SCENARIO_COLUMNS, "项目一级行业 与政策行业码表相同 枚举值：码表") == "industry_l1"
    assert header_to_field(SCENARIO_COLUMNS, "场景类型 0-业务场景 1-产品场景") == "scenario_type"
    assert header_to_field(AREA_CODE_COLUMNS, "省份名称") == "prov_name"
    assert header_to_field(AREA_CODE_COLUMNS, "区县编码") == "county_id"


def test_parse_policy_type_sheet() -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "政策类型枚举值"
    sheet.append(["序号", "政策类型", "定义"])
    sheet.append(["1", "顶层规划类", "纲领性文件"])
    raw = BytesIO()
    book.save(raw)
    items = parse_sheet(raw.getvalue(), POLICY_TYPE_COLUMNS, subject="码表")
    assert items[0]["type_name"] == "顶层规划类"
    assert items[0]["seq_no"] == "1"
    assert items[0]["definition"] == "纲领性文件"


def test_parse_skips_leading_blank_rows() -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "政策类型枚举值"
    sheet.append([None, None, None])
    sheet.append([None, None, None])
    sheet.append(["序号", "政策类型", "定义"])
    sheet.append(["1", "顶层规划类", "纲领性文件"])
    raw = BytesIO()
    book.save(raw)
    items = parse_sheet(raw.getvalue(), POLICY_TYPE_COLUMNS, subject="码表")
    assert items[0]["type_name"] == "顶层规划类"


def test_parse_real_policy_type_enum_sheet() -> None:
    path = Path(__file__).resolve().parents[3] / "docs" / "政策基础信息表_0916-更新穿透词(1).xlsx"
    if not path.exists():
        pytest.skip("本地政策类型 Excel 未入库")
    items = parse_sheet(path.read_bytes(), POLICY_TYPE_COLUMNS, subject="码表")
    if not items or items[0].get("type_name") != "顶层规划类":
        pytest.skip("第一个 sheet 不是政策类型表")


def test_content_hash_stable() -> None:
    left = dict.fromkeys(SCENARIO_FIELDS, "")
    left["scenario_tag"] = "AI安监"
    right = dict(left)
    assert content_hash(left, SCENARIO_FIELDS) == content_hash(right, SCENARIO_FIELDS)


def test_parse_area_sql_inserts() -> None:
    sql = """
create table cfg_all_area_code_info (id int);
INSERT INTO configuration.cfg_all_area_code_info (prov_id, prov_name, city_id, city_name, county_id, county_name, alias_prov_name, alias_city_name, alias_county_name, city_name_short, county_name_short) VALUES ('11', '北京市', '1101', '北京市', '110101', '东城区', '北京市', '北京市', '东城区', '北京', '东城');
INSERT INTO configuration.cfg_all_area_code_info (prov_id, prov_name, city_id, city_name, county_id, county_name, alias_prov_name, alias_city_name, alias_county_name, city_name_short, county_name_short) VALUES ('11', '北京市', '1101', '北京市', '110101', '东城区', '北京市', '北京市', '东城区', '北京', '东城');
"""
    rows = parse_area_sql(sql)
    assert len(rows) == 1
    assert rows[0]["county_id"] == "110101"
    assert rows[0]["county_name"] == "东城区"
    assert rows[0]["city_name_short"] == "北京"


_CATALOG = [
    AreaSnap("11", "北京市", "1101", "北京市", "110101", "东城区", "北京市", "北京市", "东城区", "北京", "东城"),
    AreaSnap("11", "北京市", "1101", "北京市", "110105", "朝阳区", "北京市", "北京市", "朝阳区", "北京", "朝阳"),
    AreaSnap("22", "吉林省", "2201", "长春市", "220104", "朝阳区", "吉林省", "长春市", "朝阳区", "长春", "朝阳"),
]


def test_match_three_two_one_levels() -> None:
    triple = match_area(_CATALOG, "北京市", "北京市", "朝阳区")
    assert triple.ok and triple.level == 3
    assert (triple.province_code, triple.city_code, triple.district_code) == ("11", "1101", "110105")

    city = match_area(_CATALOG, "北京", "北京", "")
    assert city.ok and city.level == 2
    assert (city.province_code, city.city_code, city.district_code) == ("11", "1101", "")

    province = match_area(_CATALOG, "北京", "", "")
    assert province.ok and province.level == 1
    assert (province.province_code, province.city_code, province.district_code) == ("11", "", "")


def test_match_does_not_guess_duplicate_county() -> None:
    result = match_area(_CATALOG, "", "", "朝阳区")
    assert result.ok is False
    assert "不唯一" in result.reason


def test_resolve_workbook_writes_reason() -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["省份", "地市", "区县"])
    sheet.append(["", "", "朝阳区"])
    raw = BytesIO()
    book.save(raw)
    payload, matched, unmatched = build_resolve_workbook(raw.getvalue(), _CATALOG)
    assert matched == 0
    assert unmatched == 1
    marked = parse_sheet(payload, AREA_CODE_COLUMNS, subject="码表")
    assert "不唯一" in marked[0]["skip_reason"]


def test_resolve_header_does_not_misread_alias_or_level_columns() -> None:
    from app.application.area_resolve import _header_role

    assert _header_role("省份（必填）") == "province_name"
    assert _header_role("城市 *") == "city_name"
    assert _header_role("省份别名") is None
    assert _header_role("城市简称") is None
    assert _header_role("区县简称") is None
    assert _header_role("城市等级") is None


def test_resolve_skips_rows_with_site_code() -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["网站编码", "省份", "地市", "区县", "省份编码", "地市编码", "区县编码"])
    sheet.append(["11010500001", "", "", "朝阳区", "", "", ""])
    sheet.append(["", "北京市", "北京市", "朝阳区", "", "", ""])
    raw = BytesIO()
    book.save(raw)
    payload, matched, unmatched = build_resolve_workbook(raw.getvalue(), _CATALOG)
    assert matched == 2
    assert unmatched == 0
    marked = parse_sheet(payload, AREA_CODE_COLUMNS, subject="码表")
    assert marked[0]["skip_reason"] == "通过"
    assert not marked[0].get("county_id")
    assert marked[1]["skip_reason"] == "通过"
    assert marked[1]["county_id"] == "110105"


def test_parse_uses_first_sheet_only() -> None:
    book = Workbook()
    first = book.active
    first.title = "全部数据"
    first.append(["序号", "政策类型", "定义"])
    first.append(["1", "顶层规划类", "纲领"])
    other = book.create_sheet("政策类型枚举值")
    other.append(["序号", "政策类型", "定义"])
    other.append(["9", "不该读到", "x"])
    raw = BytesIO()
    book.save(raw)
    items = parse_sheet(raw.getvalue(), POLICY_TYPE_COLUMNS)
    assert items[0]["type_name"] == "顶层规划类"


def test_indexed_match_handles_many_rows() -> None:
    from app.application.area_match import build_area_index, match_area_indexed

    catalog = _CATALOG * 800
    index = build_area_index(catalog)
    for _ in range(2000):
        result = match_area_indexed(index, "北京市", "北京市", "朝阳区")
        assert result.ok and result.district_code == "110105"


def test_match_falls_back_to_province() -> None:
    result = match_area(_CATALOG, "北京", "", "不存在区")
    assert result.ok is True
    assert result.level == 1
    assert result.province_code == "11"
    assert "区县不标准" in result.reason


def test_resolve_drops_a_leftover_district_code_from_another_place() -> None:
    """只匹配到地市一级时，原来会留下文件里别处的区县编码还标「通过」；信源入库以区县为准，就存成了别省的编码。"""

    book = Workbook()
    sheet = book.active
    sheet.append(["省份", "地市", "区县", "省份编码", "地市编码", "区县编码"])
    sheet.append(["北京市", "北京市", "", "", "", "320102"])
    raw = BytesIO()
    book.save(raw)
    payload, matched, _ = build_resolve_workbook(raw.getvalue(), _CATALOG)
    marked = parse_sheet(payload, AREA_CODE_COLUMNS, subject="码表")
    assert matched == 1 and marked[0]["skip_reason"] == "通过"
    assert not marked[0].get("county_id")


def _resolved(header: list[str], row: list[str]) -> tuple[list[str], list[str]]:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    sheet.append(row)
    raw = BytesIO()
    book.save(raw)
    payload, _, _ = build_resolve_workbook(raw.getvalue(), _CATALOG)
    sheet_out = load_workbook(BytesIO(payload)).active
    rows = [[str(cell.value or "") for cell in line] for line in sheet_out.iter_rows()]
    return rows[0], rows[1]


def test_resolve_drops_a_leftover_code_when_only_the_province_matched() -> None:
    """只配上省份（2 位）时，原来位数不够就把别处的地市、区县编码原样留着还标「通过」，到信源导入又被拒。"""

    header, row = _resolved(
        ["省份", "地市", "区县", "省份编码", "地市编码", "区县编码"], ["吉林省", "宁城", "", "", "1101", "110101"]
    )
    values = dict(zip(header, row, strict=False))
    assert (values["省份编码"], values["地市编码"], values["区县编码"], values["校验说明"]) == ("22", "", "", "通过")


def test_resolve_writes_into_the_exact_code_column_when_two_columns_match() -> None:
    """表头有「区县编码」「区县编码（旧）」：补出的编码写进「区县编码」，信源导入认的就是它。"""

    header, row = _resolved(
        ["省份", "地市", "区县", "区县编码", "区县编码（旧）"], ["北京市", "北京市", "朝阳区", "", "999999"]
    )
    values = dict(zip(header, row, strict=False))
    assert (values["区县编码"], values["区县编码（旧）"]) == ("110105", "999999")
