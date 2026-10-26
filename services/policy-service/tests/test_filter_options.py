"""政策几百万条时的筛选项：名称类字段输入关键词查找、不预取候选值；政策类型的候选值取政策类型码表。"""

from __future__ import annotations

from typing import Any

import pytest
from platform_common.errors import DependencyUnavailableError

from app.common import internal_clients
from app.policy.application import base_tags as service
from app.policy.application import interpretations as interpretation_service
from app.policy.repositories import interpretations as interpretation_repo
from app.policy.repositories import options as options_repo


async def test_long_text_fields_are_searched_not_listed() -> None:
    assert {"policy_name", "policy_types"}.isdisjoint(options_repo.BASE_TAG_OPTION_COLUMNS)
    assert {"policy_title", "industry_scenario_code", "industry_l1", "scenario_l1_name"}.isdisjoint(
        options_repo.INTERPRETATION_OPTION_COLUMNS
    )
    # 行业场景编码不再是筛选条件；政策原文名称仍按关键词模糊匹配。
    assert "industry_scenario_code" not in interpretation_repo.FILTER_COLUMNS
    assert "policy_title" in interpretation_repo.FILTER_COLUMNS


async def test_policy_type_options_come_from_the_code_table(monkeypatch: pytest.MonkeyPatch) -> None:
    async def preview(_session: Any) -> dict[str, Any]:
        return {"options": {"province_name": {"items": ["北京市"], "truncated": False}}}

    async def names() -> list[str]:
        return ["信息化建设类", "产业发展类"]

    monkeypatch.setattr(options_repo, "base_tag_options", preview)
    monkeypatch.setattr(internal_clients, "policy_type_names", names)
    data = await service.list_base_tag_options(None)  # type: ignore[arg-type]
    assert data["options"]["policy_types"] == {"items": ["信息化建设类", "产业发展类"], "truncated": False}
    assert data["options"]["province_name"]["items"] == ["北京市"]

    async def down() -> list[str]:
        raise DependencyUnavailableError("码表服务暂时不可用")

    # 码表服务取不到时列表页照常打开，只是政策类型没有候选值。
    monkeypatch.setattr(internal_clients, "policy_type_names", down)
    data = await service.list_base_tag_options(None)  # type: ignore[arg-type]
    assert data["options"]["policy_types"] == {"items": [], "truncated": False}


async def test_policy_type_names_are_deduplicated_in_code_table_order(monkeypatch: pytest.MonkeyPatch) -> None:
    async def codebook(_method: str, _path: str, **_: Any) -> dict[str, str]:
        return {"text": "政策类型名称\t说明\n信息化建设类\t甲\n产业发展类\t乙\n信息化建设类\t丙\n\n"}

    monkeypatch.setattr(internal_clients, "codebook", codebook)
    assert await internal_clients.policy_type_names() == ["信息化建设类", "产业发展类"]


async def test_level_one_industry_and_scenario_options_come_from_the_code_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def preview(_session: Any) -> dict[str, Any]:
        return {"options": {"info_level": {"items": ["高"], "truncated": False}}}

    async def codebook(_method: str, path: str, **_: Any) -> dict[str, str]:
        assert path.endswith("/scenario_l1")
        return {"text": "一级行业\t一级场景\n教育\t智慧校园\n教育\t在线教育\n医疗\t智慧校园\n"}

    monkeypatch.setattr(options_repo, "interpretation_options", preview)
    monkeypatch.setattr(internal_clients, "codebook", codebook)
    data = await interpretation_service.list_interpretation_options(None)  # type: ignore[arg-type]
    assert data["options"]["industry_l1"] == {"items": ["教育", "医疗"], "truncated": False}
    assert data["options"]["scenario_l1_name"] == {"items": ["智慧校园", "在线教育"], "truncated": False}

    async def down(_method: str, _path: str, **_: Any) -> dict[str, str]:
        raise DependencyUnavailableError("码表服务暂时不可用")

    monkeypatch.setattr(internal_clients, "codebook", down)
    data = await interpretation_service.list_interpretation_options(None)  # type: ignore[arg-type]
    assert data["options"]["industry_l1"]["items"] == [] and data["options"]["info_level"]["items"] == ["高"]
