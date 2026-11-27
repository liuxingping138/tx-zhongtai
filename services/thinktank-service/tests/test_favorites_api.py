"""统一「我的收藏」测试：实时跨子库鉴权、二维资料库范围过滤、计数与合并排序分页、HTTP 路由。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes
from sqlalchemy.dialects import postgresql

from app.core.database import get_db_session
from app.favorites.api import routes as favorites_routes
from app.favorites.application import favorites as fav_service
from app.favorites.domain.access import FavoritesAccess, FavoritesQuery
from app.favorites.repositories import favorites as fav_repo
from app.favorites.repositories.favorites import FavoriteRow
from app.main import app

ACTOR = Actor(id="u1", name="测试用户")
T1 = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)


def _sql_text(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _RecordingSession:
    def __init__(self, scalars: list[int], rows: list[dict[str, Any]]) -> None:
        self.stmts: list[Any] = []
        self._scalars = list(scalars)
        self._rows = rows

    async def scalar(self, stmt: Any) -> int:
        self.stmts.append(stmt)
        return self._scalars.pop(0) if self._scalars else 0

    async def execute(self, stmt: Any) -> _FakeResult:
        self.stmts.append(stmt)
        return _FakeResult(self._rows)


def test_favorites_access_from_levels() -> None:
    access = FavoritesAccess.from_levels(
        {
            "thinktank.knowledge": "READ",
            "thinktank.knowledge.download": "READ",
            "thinktank.file_type.product": "FULL",
            "thinktank.industry_type.edu": "FULL",
            "thinktank.reports": "EXPORT",
            "thinktank.proposals.download": "READ",
        }
    )
    assert access.can_read_knowledge is True
    assert access.knowledge is not None
    # 资料库模块级 READ 封顶，export 为 False，但开通独立下载权后可下载范围内文件
    assert access.knowledge.can_read_record("产品", "教育") is True
    assert access.knowledge.can_download_record("产品", "教育") is True
    assert access.knowledge.can_export_record("产品", "教育") is False
    # 报告库仅有 EXPORT 无独立下载权：可导出不可下载
    assert (
        access.can_read_reports is True and access.reports_can_export is True and access.reports_can_download is False
    )
    # 方案库无主查看权即使残留 .download 也不可读不可下载
    assert (
        access.can_read_proposals is False
        and access.proposals_can_export is False
        and access.proposals_can_download is False
    )


async def test_favorites_repo_only_queries_permitted_libraries() -> None:
    # 仅授权资料库（含二维范围）和报告库，未授权方案库 -> SQL 绝不触碰 thinktank_proposal_*
    access = FavoritesAccess.from_levels(
        {
            "thinktank.knowledge": "EXPORT",
            "thinktank.file_type.product": "EXPORT",
            "thinktank.industry_type.edu": "EXPORT",
            "thinktank.reports": "READ",
        }
    )
    k_id, r_id = uuid.uuid4(), uuid.uuid4()
    session = _RecordingSession(
        scalars=[1, 2],
        rows=[
            {
                "id": r_id,
                "library": "reports",
                "title": "行业报告",
                "category_label": "专题报告",
                "industry_label": "金融",
                "region_label": "广东省",
                "file_suffix": "PDF",
                "file_size_bytes": 2048,
                "favorited_at": T2,
                "updated_at": T2,
            },
            {
                "id": k_id,
                "library": "knowledge",
                "title": "产品手册.pdf",
                "category_label": "产品",
                "industry_label": "教育",
                "region_label": "集团",
                "file_suffix": "PDF",
                "file_size_bytes": 1024,
                "favorited_at": T1,
                "updated_at": T1,
            },
        ],
    )
    rows, counts = await fav_repo.list_unified_favorites(
        session,  # type: ignore[arg-type]
        user_id="u1",
        access=access,
        query=FavoritesQuery(library="all", keyword="报告", page=1, page_size=20),
    )
    assert counts == {"all": 3, "knowledge": 1, "reports": 2, "proposals": 0}
    assert len(rows) == 2
    all_sql = "\n".join(_sql_text(s) for s in session.stmts)
    assert "thinktank_knowledge_files" in all_sql
    assert "thinktank_report_files" in all_sql
    assert "thinktank_proposal_files" not in all_sql
    assert "UNION ALL" in all_sql
    assert "ORDER BY" in all_sql

    # 请求未授权的子库 tab 时，计数仍准确，items 为空且不执行合并查询
    session2 = _RecordingSession(scalars=[1, 2], rows=[])
    rows2, counts2 = await fav_repo.list_unified_favorites(
        session2,  # type: ignore[arg-type]
        user_id="u1",
        access=access,
        query=FavoritesQuery(library="proposals", keyword=None, page=1, page_size=20),
    )
    assert rows2 == []
    assert counts2 == {"all": 3, "knowledge": 1, "reports": 2, "proposals": 0}
    assert len(session2.stmts) == 2  # 仅跑两条 count，不跑 union 查询


async def test_favorites_service_formats_items_and_can_export(monkeypatch: pytest.MonkeyPatch) -> None:
    access = FavoritesAccess.from_levels(
        {
            "thinktank.knowledge": "FULL",
            "thinktank.file_type.product": "READ",
            "thinktank.file_type.undefined": "EXPORT",
            "thinktank.industry_type.none": "EXPORT",
            "thinktank.reports": "READ",
            "thinktank.reports.download": "READ",
            "thinktank.proposals": "EXPORT",
        }
    )
    k_id, r_id, p_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fake_rows = [
        FavoriteRow(p_id, "proposals", "交通方案", "售前方案", "交通物流", "江苏省", "PPT", 4096, T2, T2),
        FavoriteRow(r_id, "reports", "行业洞察", "专题报告", "党政", "广东省", "PDF", 2048, T1, T1),
        FavoriteRow(k_id, "knowledge", "未分类资料.pdf", "", "", "集团", "PDF", 1024, T1, T1),
    ]
    monkeypatch.setattr(
        fav_service.repo,
        "list_unified_favorites",
        AsyncMock(return_value=(fake_rows, {"all": 3, "knowledge": 1, "reports": 1, "proposals": 1})),
    )

    result = await fav_service.list_favorites(
        AsyncMock(), actor=ACTOR, access=access, query=FavoritesQuery(library="all", keyword=None, page=1, page_size=20)
    )
    assert result["total"] == 3
    assert result["counts"] == {"all": 3, "knowledge": 1, "reports": 1, "proposals": 1}
    p_item, r_item, k_item = result["items"]
    assert p_item["library_label"] == "方案库"
    assert p_item["can_export"] is True and p_item["can_download"] is False
    assert p_item["preview_path"] == f"/thinktank/proposals/{p_id}"
    assert r_item["library_label"] == "报告库"
    assert r_item["can_export"] is False and r_item["can_download"] is True
    assert r_item["preview_path"] == f"/thinktank/reports/{r_id}"
    assert k_item["library_label"] == "资料库"
    assert k_item["category_label"] == "未定义"
    assert k_item["can_export"] is True and k_item["can_download"] is False
    assert k_item["preview_path"] == f"/thinktank/knowledge/{k_id}"


def test_favorites_http_route(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[favorites_routes.get_favorites_access] = lambda: FavoritesAccess(reports_level="FULL")
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"actor", "_"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR

    monkeypatch.setattr(
        favorites_routes.service,
        "list_favorites",
        AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 20,
                "counts": {"all": 0, "knowledge": 0, "reports": 0, "proposals": 0},
            }
        ),
    )
    try:
        client = TestClient(app)
        res = client.get("/api/v1/thinktank/favorites", params={"library": "reports", "keyword": "洞察"})
        assert res.status_code == 200
        assert res.json()["data"]["counts"] == {"all": 0, "knowledge": 0, "reports": 0, "proposals": 0}
        assert client.get("/api/v1/thinktank/favorites", params={"library": "invalid"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
