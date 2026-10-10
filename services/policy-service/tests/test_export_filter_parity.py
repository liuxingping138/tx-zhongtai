"""导出与列表的筛选条件必须一致。

「所见即所导」靠三处对齐：列表接口的 query 参数、导出接口的 query 参数、
仓储里的 FILTER_COLUMNS。任何一处加了字段而另外两处没跟上，这里就会失败。
"""

from __future__ import annotations

import os

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "unit-test")

import pytest
from fastapi.routing import APIRoute

from app.crawler.repositories import crawler, crawler_v2
from app.main import app
from app.policy.repositories import base_tags, interpretations, sources

PAGING = {"page", "page_size"}

TABLES = [
    ("/api/v1/policy/sources", sources),
    ("/api/v1/policy/base-tags", base_tags),
    ("/api/v1/policy/interpretations", interpretations),
    ("/api/v1/policy/crawler-monitoring/tasks", crawler),
    ("/api/v1/policy/crawler-monitoring-v2/sites", crawler_v2),
]

# 爬虫监测除了模糊匹配的列，还有状态精确匹配和停更天数下限，它们不在 FILTER_COLUMNS 里。
EXTRA_FILTERS = {
    "/api/v1/policy/crawler-monitoring/tasks": {"health_status", "stale_days_min", "abnormal_only"},
    "/api/v1/policy/crawler-monitoring-v2/sites": {"status"},
}


def _query_params(path: str) -> set[str]:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and "GET" in route.methods:
            return {p.name for p in route.dependant.query_params}
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
