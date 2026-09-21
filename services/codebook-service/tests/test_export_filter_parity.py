"""导出与列表的筛选条件必须一致。

「所见即所导」靠列表接口与导出接口的 query 参数对齐；
任何一处加了字段而另一处没跟上，这里就会失败。
"""

from __future__ import annotations

import os

os.environ.setdefault("CODEBOOK_DATABASE_URL", "postgresql+asyncpg://codebook_app:test@localhost:5432/codebook_db")
os.environ.setdefault("CODEBOOK_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("CODEBOOK_AUDIT_INGEST_SECRET", "unit-test")

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402
from app.repositories import area_codes, policy_types, scenarios  # noqa: E402

PAGING = {"page", "page_size"}

# policy_types 只有一个 keyword，跨三列 or 匹配，没有 FILTER_COLUMNS 映射。
TABLES = [
    ("/api/v1/codebook/scenarios", scenarios, True),
    ("/api/v1/codebook/area-codes", area_codes, True),
    ("/api/v1/codebook/policy-types", policy_types, False),
]


def _query_params(path: str) -> set[str]:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and "GET" in route.methods:
            return {p.name for p in route.dependant.query_params}
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
