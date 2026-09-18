from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.application.excel import parse_sheet
from app.domain.fields import POLICY_TYPE_COLUMNS, SCENARIO_COLUMNS, header_to_field
from app.domain.models import SCENARIO_FIELDS, content_hash


def test_header_matches_user_excel_titles() -> None:
    assert header_to_field(POLICY_TYPE_COLUMNS, "政策类型") == "type_name"
    assert header_to_field(SCENARIO_COLUMNS, "行业场景编码") == "industry_scenario_code"
    assert header_to_field(SCENARIO_COLUMNS, "项目一级行业 与政策行业码表相同 枚举值：码表") == "industry_l1"
    assert header_to_field(SCENARIO_COLUMNS, "场景类型 0-业务场景 1-产品场景") == "scenario_type"


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
