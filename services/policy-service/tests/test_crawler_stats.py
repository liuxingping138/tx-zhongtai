"""爬虫监测图表：省份归并、趋势补零、近 7 天对比窗口。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes

from app.core.database import get_db_session
from app.crawler.application import crawler_stats as stats
from app.crawler.application import crawler_status as status_history
from app.crawler.domain.provinces import EMPTY_PROVINCE, chart_province
from app.crawler.repositories import crawler_stats as repo
from app.main import app

_ACTOR = Actor(id="00000000-0000-0000-0000-000000000001", name="测试")
YESTERDAY = date(2026, 10, 11)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("新疆维吾尔族自治区", "新疆维吾尔自治区"),
        ("新疆", "新疆维吾尔自治区"),
        ("广西自治区", "广西壮族自治区"),
        ("西藏藏族自治区", "西藏自治区"),
        ("上海", "上海市"),
        ("内蒙古自治区", "内蒙古自治区"),
        ("黑龙江省", "黑龙江省"),
        ("山西省", "山西省"),
        ("山东省", "山东省"),
        ("  ", EMPTY_PROVINCE),
        ("全国", "全国"),
        ("国央企", "国央企"),
    ],
)
def test_chart_province_merges_spellings_and_keeps_non_provinces(raw: str, expected: str) -> None:
    assert chart_province(raw) == expected


def test_provinces_merge_counts_and_keep_raw_names_for_filtering() -> None:
    rows = [
        ("新疆维吾尔族自治区", 10, 2, 20),
        ("新疆维吾尔自治区", 1, 0, 54),
        ("新疆", 0, 0, 2),
        ("广东省", 800, 21, 132),
    ]
    items = stats.merge_provinces(rows)
    assert items[0] == {
        "name": "广东省",
        "raw_names": ["广东省"],
        "normal": 800,
        "watch": 21,
        "stale": 132,
        "sites": 953,
    }
    xinjiang = items[1]
    assert xinjiang["name"] == "新疆维吾尔自治区"
    assert xinjiang["raw_names"] == ["新疆", "新疆维吾尔族自治区", "新疆维吾尔自治区"]
    assert (xinjiang["stale"], xinjiang["sites"]) == (76, 89)


def test_fill_series_keeps_gap_days_as_zero() -> None:
    items = stats.fill_series(
        date(2026, 10, 1), date(2026, 10, 3), [(date(2026, 10, 1), 5, 2), (date(2026, 10, 3), 7, 3)]
    )
    assert items == [
        {"date": "2026-10-01", "rows": 5, "sites": 2},
        {"date": "2026-10-02", "rows": 0, "sites": 0},
        {"date": "2026-10-03", "rows": 7, "sites": 3},
    ]


async def test_recent_rows_compares_two_full_weeks_ending_yesterday(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "yesterday", lambda: YESTERDAY)
    range_rows = AsyncMock(side_effect=[700, 500])
    monkeypatch.setattr(repo, "range_rows", range_rows)
    assert await stats.recent_rows(AsyncMock()) == {"days": 7, "rows": 700, "previous_rows": 500}
    windows = [call.args[1:] for call in range_rows.await_args_list]
    assert windows == [(date(2026, 10, 5), date(2026, 10, 11)), (date(2026, 9, 28), date(2026, 10, 4))]


async def test_trend_ends_yesterday_and_spans_requested_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "yesterday", lambda: YESTERDAY)
    monkeypatch.setattr(repo, "daily_series", AsyncMock(return_value=[]))
    result = await stats.trend(AsyncMock(), 30)
    assert (result["date_from"], result["date_to"], len(result["items"])) == ("2026-09-12", "2026-10-11", 30)


async def test_health_reports_long_stale_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    buckets = {"normal": 1, "watch": 2, "stale_recent": 3, "stale_long": 4}
    monkeypatch.setattr(repo, "health_buckets", AsyncMock(return_value=buckets))
    assert await stats.health(AsyncMock()) == {**buckets, "long_stale_days": stats.LONG_STALE_DAYS}


def _trend_client(monkeypatch: pytest.MonkeyPatch, route_name: str = "trend") -> tuple[TestClient, AsyncMock]:
    route = next(item for item in iter_api_routes(app) if item.path.endswith(f"/crawler-monitoring-v2/{route_name}"))
    app.dependency_overrides[get_db_session] = _db
    for dep in route.dependant.dependencies:
        if dep.name == "_":
            app.dependency_overrides[dep.call] = lambda: _ACTOR
    trend = AsyncMock(return_value={"date_from": "", "date_to": "", "items": []})
    monkeypatch.setattr(stats, "trend", trend)
    return TestClient(app), trend


async def _db():  # type: ignore[no-untyped-def]
    yield None


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_trend_route_accepts_query_string_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """查询串里的天数是字符串，曾因 Literal 不做转换导致页面每次请求都 422。"""

    client, trend = _trend_client(monkeypatch)
    response = client.get("/api/v1/policy/crawler-monitoring-v2/trend", params={"days": "30"})
    assert response.status_code == 200
    assert trend.await_args is not None and trend.await_args.args[1] == 30


def test_trend_route_rejects_unsupported_range(monkeypatch: pytest.MonkeyPatch) -> None:
    client, trend = _trend_client(monkeypatch)
    response = client.get("/api/v1/policy/crawler-monitoring-v2/trend", params={"days": "7"})
    assert response.status_code == 422
    assert "30、90、365" in response.json()["message"]
    trend.assert_not_awaited()


def test_site_trend_route_passes_raw_identity_and_validates_days(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _trend_client(monkeypatch, "site-trend")
    site_trend = AsyncMock(return_value={"date_from": "", "date_to": "", "items": []})
    monkeypatch.setattr(status_history, "site_trend", site_trend)
    url = "/api/v1/policy/crawler-monitoring-v2/site-trend"
    response = client.get(url, params={"site_name": "市财政局", "province_name": "新疆", "days": "90"})
    assert response.status_code == 200
    assert site_trend.await_args is not None
    assert site_trend.await_args.kwargs == {
        "site_name": "市财政局",
        "province_name": "新疆",
        "city_name": "",
        "days": 90,
    }
    assert client.get(url, params={"site_name": "市财政局", "days": "14"}).status_code == 422
    assert client.get(url, params={"days": "90"}).status_code == 422
