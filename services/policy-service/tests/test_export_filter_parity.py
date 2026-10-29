"""导出与列表的筛选条件必须一致。

「所见即所导」靠三处对齐：列表接口的 query 参数、导出接口的 query 参数、
仓储里的 FILTER_COLUMNS。任何一处加了字段而另外两处没跟上，这里就会失败。
"""

from __future__ import annotations

import pytest
from platform_common.route_audit import iter_api_routes, query_param_names

from app.crawler.repositories import crawler_sites
from app.main import app
from app.policy.repositories import base_tags, interpretations, sources

PAGING = {"page", "page_size"}

TABLES = [
    ("/api/v1/policy/sources", sources),
    ("/api/v1/policy/base-tags", base_tags),
    ("/api/v1/policy/interpretations", interpretations),
    ("/api/v1/policy/crawler-monitoring/sites", crawler_sites),
]

# 爬虫监测的状态、基础标签的打标状态是精确匹配，信源的上线时间是区间，都不在 FILTER_COLUMNS 里。
EXTRA_FILTERS = {
    "/api/v1/policy/crawler-monitoring/sites": {"status"},
    "/api/v1/policy/base-tags": {"ai_status"},
    "/api/v1/policy/sources": set(sources.DATE_RANGE_FILTERS),
}


def _query_params(path: str) -> set[str]:
    for route in iter_api_routes(app):
        if route.path == path and "GET" in route.methods:
            return query_param_names(route)
    raise AssertionError(f"未找到路由 {path}")


@pytest.mark.parametrize(("prefix", "repo"), TABLES)
def test_export_accepts_the_same_filters_as_list(prefix: str, repo) -> None:
    list_filters = _query_params(prefix) - PAGING
    export_filters = _query_params(f"{prefix}/export")
    assert list_filters == export_filters, f"{prefix}：列表与导出的筛选参数不一致"


@pytest.mark.parametrize(("prefix", "repo"), TABLES)
def test_filters_match_repository_columns(prefix: str, repo) -> None:
    assert _query_params(prefix) - PAGING - EXTRA_FILTERS.get(prefix, set()) == set(repo.FILTER_COLUMNS)


@pytest.mark.parametrize(("prefix", "repo"), TABLES)
def test_unknown_filter_key_is_rejected(prefix: str, repo) -> None:
    """未知字段必须报错，不能被静默忽略——否则导出会悄悄导出全表。"""

    with pytest.raises(KeyError):
        repo._conditions({"zz_not_a_column": "x"})


def test_unknown_ai_status_is_a_422_not_a_500() -> None:
    """打标状态改过名后，旧书签、旧链接里还带着旧值：原来查询时 KeyError 成 500。"""

    from platform_common.errors import ApiError

    from app.policy.api.base_tags import base_tag_filters

    with pytest.raises(ApiError) as caught:
        base_tag_filters(None, None, None, None, None, ["打标中"])
    assert caught.value.http_status == 422 and "打标中" in caught.value.message
    assert base_tag_filters(None, None, None, None, None, ["待解读"])["ai_status"] == ["待解读"]
