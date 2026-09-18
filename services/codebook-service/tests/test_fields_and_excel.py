from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.application.area_match import AreaSnap, match_area
from app.application.area_sql import parse_area_sql
from app.application.excel import parse_sheet
from app.domain.fields import AREA_CODE_COLUMNS, POLICY_TYPE_COLUMNS, SCENARIO_COLUMNS, header_to_field
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
    items = parse_sheet(raw.getvalue(), POLICY_TYPE_COLUMNS, sheet_name="政策类型枚举值")
    assert items == [{"seq_no": "1", "type_name": "顶层规划类", "definition": "纲领性文件"}]


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
    items = parse_sheet(raw.getvalue(), POLICY_TYPE_COLUMNS, sheet_name="政策类型枚举值")
    assert items[0]["type_name"] == "顶层规划类"


def test_parse_real_policy_type_enum_sheet() -> None:
    path = Path(__file__).resolve().parents[3] / "docs" / "政策基础信息表_0916-更新穿透词(1).xlsx"
    if not path.exists():
        pytest.skip("本地政策类型 Excel 未入库")
    items = parse_sheet(path.read_bytes(), POLICY_TYPE_COLUMNS, sheet_name="政策类型枚举值")
    assert len(items) == 26
    assert items[0]["type_name"] == "顶层规划类"
    assert items[-1]["type_name"] == "能源管理类"


def test_content_hash_stable() -> None:
    left = {field: "" for field in SCENARIO_FIELDS}
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


def test_match_falls_back_to_province() -> None:
    result = match_area(_CATALOG, "北京", "", "不存在区")
    assert result.ok is True
    assert result.level == 1
    assert result.province_code == "11"
    assert "区县不标准" in result.reason
