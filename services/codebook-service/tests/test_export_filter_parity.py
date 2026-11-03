"""导出与列表的筛选条件必须一致。

「所见即所导」靠列表接口与导出接口的 query 参数对齐；
任何一处加了字段而另一处没跟上，这里就会失败。
"""

from __future__ import annotations

import pytest
from platform_common.route_audit import iter_api_routes, query_param_names

from app.main import app
from app.repositories import area_codes, policy_types, scenarios

PAGING = {"page", "page_size"}

# policy_types 只有一个 keyword，跨三列 or 匹配，没有 FILTER_COLUMNS 映射。
TABLES = [
    ("/api/v1/codebook/scenarios", scenarios, True),
    ("/api/v1/codebook/area-codes", area_codes, True),
    ("/api/v1/codebook/policy-types", policy_types, False),
]


def _query_params(path: str) -> set[str]:
    for route in iter_api_routes(app):
        if route.path == path and "GET" in route.methods:
            return query_param_names(route)
    raise AssertionError(f"未找到路由 {path}")


@pytest.mark.parametrize(("prefix", "repo", "has_columns"), TABLES)
def test_export_accepts_the_same_filters_as_list(prefix: str, repo, has_columns: bool) -> None:
    assert _query_params(prefix) - PAGING == _query_params(f"{prefix}/export"), f"{prefix}：列表与导出筛选参数不一致"


@pytest.mark.parametrize(("prefix", "repo", "has_columns"), TABLES)
def test_filters_match_repository_columns(prefix: str, repo, has_columns: bool) -> None:
    if not has_columns:
        pytest.skip("policy_types 走单关键词 or 匹配，没有列映射")
    assert _query_params(prefix) - PAGING == set(repo.FILTER_COLUMNS)


@pytest.mark.parametrize(("prefix", "repo", "has_columns"), TABLES)
def test_unknown_filter_key_is_rejected(prefix: str, repo, has_columns: bool) -> None:
    """未知字段必须报错，不能被静默忽略——否则导出会悄悄导出全表。"""

    with pytest.raises(KeyError):
        repo._conditions({"zz_not_a_column": "x"})


def test_scenario_name_matches_any_level() -> None:
    """按场景名称查：一级、二级、三级场景名称任一包含关键词就算，多个关键词也是「或」。"""

    from sqlalchemy.dialects import postgresql

    (cond,) = scenarios._conditions({"scenario_name": ["机场", "水务"]})
    sql = str(cond.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    for column in ("scenario_l1_name", "scenario_l2_name", "scenario_l3_name"):
        assert column in sql
    assert "机场" in sql and "水务" in sql
    assert scenarios._conditions({"scenario_name": []}) == []
