"""筛选项字段必须与列表接口的 query 参数对齐。

前端按字段名直接绑定下拉（`filters.bind('actor_name')`），
字段名对不上就会静默变成空候选。
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.repositories.events import OPTION_COLUMNS


def _query_params(path: str) -> set[str]:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and "GET" in route.methods:
            return {p.name for p in route.dependant.query_params}
    raise AssertionError(f"未找到路由 {path}")


def test_option_fields_are_list_query_params() -> None:
    assert set(OPTION_COLUMNS) <= _query_params("/api/v1/audit/events")


def test_search_endpoint_exists_and_takes_field_and_q() -> None:
    assert _query_params("/api/v1/audit/events/options/search") == {"field", "q"}


def test_actor_name_maps_to_the_snapshot_column() -> None:
    """列表按 actor_name 过滤，落库列是 actor_name_snapshot，映射不能错。"""

    assert OPTION_COLUMNS["actor_name"].key == "actor_name_snapshot"


@pytest.mark.parametrize("field", ["actor_name", "module_code", "action_code"])
def test_expected_fields_are_offered(field: str) -> None:
    assert field in OPTION_COLUMNS
