"""智库统计中心单测：领域口径、应用汇总、多工作表 Excel 导出与路由鉴权。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from platform_common.actors import Actor
from platform_common.errors import NotFoundError
from platform_common.route_audit import iter_api_routes

from app.core.database import get_db_session
from app.main import app
from app.statistics.application import export as export_svc
from app.statistics.application import statistics as stats_svc
from app.statistics.domain.specs import (
    DIMENSIONS_BY_SCOPE,
    DimensionSpec,
    StatisticsQuery,
    aggregate_classification_counts,
    compute_delta_pct,
    format_bucket_label,
    libraries_for_scope,
    parse_wan_amount,
    resolve_time_window,
)
from app.statistics.repositories import statistics as repo


def _actor() -> Actor:
    return Actor(id="u-leader", name="管理领导")


def test_resolve_time_window_presets_and_custom() -> None:
    now = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)  # 北京时间 2026-11-27 17:00
    w7 = resolve_time_window(preset="7d", date_from=None, date_to=None, now_utc=now)
    assert w7.date_from == "2026-11-21"
    assert w7.date_to == "2026-11-27"
    assert w7.days == 7
    assert w7.prev_start_utc is not None

    wq = resolve_time_window(preset="quarter", date_from=None, date_to=None, now_utc=now)
    assert wq.date_from == "2026-10-01"
    assert wq.date_to == "2026-11-27"

    wy = resolve_time_window(preset="year", date_from=None, date_to=None, now_utc=now)
    assert wy.date_from == "2026-01-01"

    wall = resolve_time_window(preset="all", date_from=None, date_to=None, now_utc=now)
    assert wall.start_utc is None
    assert wall.prev_start_utc is None

    wcustom = resolve_time_window(
        preset="30d",
        date_from=date(2026, 11, 10),
        date_to=date(2026, 11, 1),
        now_utc=now,
    )
    assert wcustom.preset == "custom"
    assert wcustom.date_from == "2026-11-01"
    assert wcustom.date_to == "2026-11-10"
    assert wcustom.days == 10


def test_classification_pipe_split_and_helpers() -> None:
    spec = DimensionSpec("industry", "行业", pipe_split=True, exclude_values=frozenset({"无"}))
    rows = [("党政|中小", 10), ("无", 99), ("党政", 5), ("", 3), ("农业", 7)]
    agg = aggregate_classification_counts(rows, spec=spec, limit=3)
    assert agg == [("党政", 15), ("中小", 10), ("其他合并", 10)]

    assert parse_wan_amount("1,280.5万元") == 1280.5
    assert parse_wan_amount("待定") == 0.0
    assert parse_wan_amount(None) == 0.0

    assert compute_delta_pct(15, 10) == 50.0
    assert compute_delta_pct(5, 0) == 100.0
    assert compute_delta_pct(0, 0) == 0.0
    assert compute_delta_pct(10, None) is None

    bkt = datetime(2026, 11, 23, 0, 0)
    assert format_bucket_label(bkt, "day") == "11-23"
    assert format_bucket_label(bkt, "week").endswith("W48")
    assert format_bucket_label(bkt, "month") == "2026-11"
    assert format_bucket_label(bkt, "quarter") == "2026 Q4"
    assert format_bucket_label(bkt, "year") == "2026年"
    assert libraries_for_scope("all") == ("knowledge", "reports", "proposals")
    assert libraries_for_scope("reports") == ("reports",)
    assert len(DIMENSIONS_BY_SCOPE["proposals"]) >= 4


def _stub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 11, 26, 8, 0, tzinfo=UTC)
    sample_doc = repo.RankedDocument(
        id=str(uuid.uuid4()),
        library="knowledge",
        title="智慧农业经分月报.pdf",
        category="经分",
        industry="农业",
        dept="政企事业部",
        file_suffix="pdf",
        file_size_bytes=1024 * 1024 * 5,
        uploader="马丽",
        uploaded_at=now,
        is_defined=True,
        downloads=12,
        previews=58,
        favorites=4,
    )
    monkeypatch.setattr(
        repo,
        "fetch_library_totals",
        AsyncMock(
            return_value={
                "knowledge": repo.LibraryAssetSummary("knowledge", 100, 95, 1024 * 1024 * 500),
                "reports": repo.LibraryAssetSummary("reports", 20, 18, 1024 * 1024 * 80),
                "proposals": repo.LibraryAssetSummary("proposals", 10, 9, 1024 * 1024 * 40),
            }
        ),
    )
    monkeypatch.setattr(
        repo,
        "fetch_behavior_summary",
        AsyncMock(
            side_effect=[
                repo.BehaviorSummary(
                    uploads=24, previews=300, downloads=36, favorites=10, unfavorites=2, governance=40, active_users=18
                ),
                repo.BehaviorSummary(
                    uploads=20, previews=240, downloads=30, favorites=8, unfavorites=1, governance=30, active_users=15
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        repo,
        "fetch_dimension_raw_counts",
        AsyncMock(return_value=[("经分", 45), ("产品", 35), ("", 5)]),
    )
    monkeypatch.setattr(
        repo,
        "fetch_proposal_win_summary",
        AsyncMock(return_value=repo.ProposalWinSummary(10, 6, 2, 1, 1, 75.0, 1200.5)),
    )
    monkeypatch.setattr(
        repo,
        "fetch_trend_series",
        AsyncMock(
            return_value=[
                repo.TrendBucket("2026-11-16", "26 W47", 10, 4, 2, 18, 140, 16, 12),
                repo.TrendBucket("2026-11-23", "26 W48", 14, 6, 3, 22, 160, 20, 18),
            ]
        ),
    )
    monkeypatch.setattr(
        repo,
        "fetch_top_documents_by_metrics",
        AsyncMock(return_value={"download": [sample_doc], "preview": [sample_doc], "favorite": [sample_doc]}),
    )
    actor_row = repo.RankedActor("u-1", "马丽", 12, 20, 80, 15, 9)
    monkeypatch.setattr(repo, "fetch_top_actors", AsyncMock(return_value=([actor_row], [actor_row])))
    monkeypatch.setattr(
        repo,
        "fetch_top_departments",
        AsyncMock(return_value=[repo.RankedDepartment("政企事业部", 80, 76)]),
    )
    monkeypatch.setattr(
        repo,
        "fetch_document_peek",
        AsyncMock(
            return_value=repo.DocumentPeekData(
                doc=sample_doc,
                recent_logs=[repo.DocumentActivityItem("张晓宇", "下载", "", now)],
            )
        ),
    )


@pytest.mark.asyncio
async def test_overview_and_excel_export(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_repo(monkeypatch)
    fake_session = AsyncMock()
    overview = await stats_svc.get_statistics_overview(fake_session, query=StatisticsQuery())
    assert overview["assets"]["total_files"] == 130
    assert overview["assets"]["undefined_files"] == 8
    assert overview["behavior"]["uploads_delta_pct"] == 20.0
    assert overview["proposal_win"]["win_rate"] == 75.0
    assert len(overview["top_documents"]["download"]) == 1

    # 导出 5 张工作表 + 审计入队
    _stub_repo(monkeypatch)
    enqueue = AsyncMock()
    monkeypatch.setattr(export_svc, "enqueue_event", enqueue)
    xlsx = await export_svc.export_statistics_excel(fake_session, actor=_actor(), query=StatisticsQuery())
    wb = load_workbook(BytesIO(xlsx))
    assert wb.sheetnames == ["总览指标", "分类分布", "行为趋势", "热门文档", "贡献排行"]
    assert enqueue.await_count == 1
    assert enqueue.await_args.kwargs["event_type"] == "thinktank.statistics.exported"


@pytest.mark.asyncio
async def test_document_detail_found_and_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_repo(monkeypatch)
    fake_session = AsyncMock()
    res = await stats_svc.get_document_detail(fake_session, library="knowledge", file_id=uuid.uuid4())
    assert res["document"]["title"] == "智慧农业经分月报.pdf"
    assert len(res["recent_logs"]) == 1

    monkeypatch.setattr(repo, "fetch_document_peek", AsyncMock(return_value=None))
    with pytest.raises(NotFoundError):
        await stats_svc.get_document_detail(fake_session, library="knowledge", file_id=uuid.uuid4())


def test_statistics_http_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(export_svc, "enqueue_event", AsyncMock())
    fake_session = SimpleNamespace(commit=AsyncMock())

    async def _fake_session():
        yield fake_session

    overrides = {get_db_session: _fake_session}
    for route in iter_api_routes(app):
        if not route.path.startswith("/api/v1/thinktank/statistics"):
            continue
        for dep in route.dependant.dependencies:
            if dep.name in {"_actor", "actor"} and dep.call is not None:
                overrides[dep.call] = _actor

    app.dependency_overrides.update(overrides)
    try:
        client = TestClient(app)
        r1 = client.get("/api/v1/thinktank/statistics?library=all&granularity=week&preset=30d")
        assert r1.status_code == 200
        body = r1.json()
        assert body["data"]["assets"]["total_files"] == 130

        r2 = client.get(f"/api/v1/thinktank/statistics/documents/knowledge/{uuid.uuid4()}")
        assert r2.status_code == 200
        assert r2.json()["data"]["document"]["library"] == "knowledge"

        _stub_repo(monkeypatch)
        r3 = client.get("/api/v1/thinktank/statistics/export?library=all&preset=30d")
        assert r3.status_code == 200
        assert "spreadsheetml.sheet" in r3.headers["content-type"]
    finally:
        app.dependency_overrides.clear()
