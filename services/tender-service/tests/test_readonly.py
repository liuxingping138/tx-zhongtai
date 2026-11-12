from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import MagicMock

import pymysql
import pytest
from fastapi.testclient import TestClient
from platform_common.errors import DependencyUnavailableError, NotFoundError
from platform_common.route_audit import audit_routes, iter_api_routes, permission_map
from pydantic import ValidationError

from app.application import counts
from app.application import records as service
from app.application import statistics as stats
from app.core import source
from app.core.config import Settings
from app.domain.fields import TABLES, columns
from app.domain.queries import ListQuery, StatsQuery
from app.main import app
from app.repositories import records, statistics


class Reader:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def select(self, sql, params=()):
        self.calls.append((sql, params))
        assert sql.startswith("SELECT ")
        return next(self.results)


@pytest.mark.parametrize("kind,status", TABLES)
def test_status_routes_to_one_table_and_never_reads_content(kind, status):
    reader = Reader([[{"id": 123}]])
    rows = records.list_records(reader, kind, ListQuery(project_status=status, page=2))
    assert rows == [{"id": 123}]
    for sql, params in reader.calls:
        assert TABLES[kind, status] in sql
        assert "project_status = %s" in sql and params[0] == status
        assert "ORDER BY public_date DESC, id DESC" in sql
        assert " content" not in sql and " JOIN " not in sql
    assert reader.calls[0][1][-2:] == (21, 20)


def test_filters_escape_keywords_bind_values_and_include_end_day():
    query = ListQuery(
        project_name="%' OR 1=1_",
        purchaser_provname=["北京", "河北"],
        purchaser_cityname=["北京市"],
        purchaser_countyname=["朝阳区"],
        project_content_id="123",
        is_supp_scene=["0"],
        collect_date_from="2026-11-01",
        collect_date_to="2026-11-12",
        public_date_to="2026-11-12",
        create_time_from="2026-11-01",
    )
    sql, params = records.where_clause(query)
    assert "OR 1=1" not in sql
    assert "%=%' OR 1==1=_%" in params
    assert "2026-11-13" in params
    assert "purchaser_provname IN (%s, %s)" in sql
    assert "create_time >= %s" in sql


@pytest.mark.parametrize(
    "values",
    [
        {"project_status": "2"},
        {"page": 0},
        {"page_size": 101},
        {"unknown": "value"},
        {"collect_date_from": "2026-11-12", "collect_date_to": "2026-11-01"},
        {"public_date_to": "9999-12-31"},
        {"is_supp_scene": ["2"]},
        {"project_name": "智慧城市"},
        {"project_name": "智慧城市", "collect_date_from": "2026-11-01"},
        {"project_name": "智慧城市", "collect_date_from": "2025-01-01", "collect_date_to": "2026-11-12"},
    ],
)
def test_invalid_filters_rejected(values):
    with pytest.raises(ValidationError):
        ListQuery(**values)


@pytest.mark.parametrize(
    "date_kwargs",
    [
        {"collect_date_from": "2026-11-01", "collect_date_to": "2026-11-12"},
        {"public_date_from": "2026-11-01", "public_date_to": "2026-11-12"},
        {"create_time_from": "2026-11-01", "create_time_to": "2026-11-12"},
    ],
)
def test_project_name_allows_bounded_date_ranges(date_kwargs):
    query = ListQuery(project_name="智慧城市", **date_kwargs)
    assert query.project_name == "智慧城市"


def test_content_uses_confirmed_uid_and_exact_original_collect_date():
    reader = Reader([[{"html": "<p>原文</p>"}]])
    result = records.read_content(reader, {"project_content_id": "a" * 32, "collect_date": "2026-11-12"})
    assert result["html"] == "<p>原文</p>"
    sql, params = reader.calls[0]
    assert "crawler2021.zhaobiao2021_prod" in sql
    assert "uid = %s AND create_time = %s" in sql
    assert params == ("a" * 32, "2026-11-12")


def test_short_numeric_id_only_reads_qlm():
    reader = Reader([[{"html": "<table>正文</table>"}]])
    records.read_content(reader, {"project_content_id": "1234567890123"})
    assert "infocontent AS html" in reader.calls[0][0]
    assert "qlm_pdf_content" in reader.calls[0][0]
    assert reader.calls[0][1] == (1234567890123,)


@pytest.mark.parametrize("reference", [{}, {"project_content_id": "12abc"}, {"project_content_id": "a" * 32}])
def test_missing_reference_does_not_scan_body_tables(reference):
    reader = Reader([])
    assert records.read_content(reader, reference) is None
    assert not reader.calls


def bind_reader(monkeypatch, target, reader):
    @contextmanager
    def fake_reader(**kwargs):
        yield reader

    monkeypatch.setattr(target, "source_reader", fake_reader)


def test_delivered_content_resolves_collect_date_from_original(monkeypatch):
    reader = Reader(
        [
            [{"id": 20, "project_content_id": "a" * 32, "collect_date": "wrong"}],
            [{"project_content_id": "a" * 32, "collect_date": "2026-11-12"}],
            [{"html": "<p>正文</p>"}],
        ]
    )
    bind_reader(monkeypatch, service, reader)
    assert service.get_content("winbid", "1", 20)["html"] == "<p>正文</p>"
    assert TABLES["winbid", "1"] in reader.calls[0][0]
    assert TABLES["winbid", "0"] in reader.calls[1][0]
    assert reader.calls[2][1][1] == "2026-11-12"


def test_bigint_ids_are_strings_and_dates_are_preserved(monkeypatch):
    reader = Reader(
        [
            [{"id": 2005511121291911170, "create_time": datetime(2026, 11, 12, 8), "collect_date": date(2026, 11, 12)}],
        ]
    )
    bind_reader(monkeypatch, service, reader)
    result = service.list_records("winbid", ListQuery())
    assert result["items"][0]["id"] == "2005511121291911170"
    assert result["items"][0]["create_time"] == "2026-11-12 08:00:00"
    assert result["items"][0]["collect_date"] == "2026-11-12"


def test_missing_record_and_body_return_404(monkeypatch):
    for fn, results in [
        (service.get_record, [[]]),
        (service.get_content, [[]]),
        (service.get_content, [[{"id": 1, "project_content_id": ""}]]),
    ]:
        bind_reader(monkeypatch, service, Reader(results))
        with pytest.raises(NotFoundError):
            fn("winbid", "0", 1)


def test_workflow_counts_equal_without_double_counting_source(monkeypatch):
    reader = Reader(
        [
            [{"province": "北京", "total": 10, "processed": 3}],
            [{"province": "北京", "total": 5, "processed": 2}],
            [],
            [],
        ]
    )
    bind_reader(monkeypatch, stats, reader)
    stats._cache.clear()
    query = StatsQuery(date_from="2026-11-11", date_to="2026-11-12")
    result = stats.get_statistics(query)
    assert result["daily"][0] == {
        "date": "2026-11-11",
        "purchaser": 10,
        "winbid": 5,
        "tagged": 5,
        "enriched": 5,
        "scenario": 0,
    }
    assert result["daily"][1]["purchaser"] == result["daily"][1]["tagged"] == 0
    assert result["provinces"][0]["tagged"] == 5
    assert stats.get_statistics(query) is result
    assert len(reader.calls) == 4
    assert all("approval" not in sql for sql, _ in reader.calls)


def test_totals_only_count_raw_tables_and_cache(monkeypatch):
    reader = Reader([[{"total": 10}], [{"total": 20}]])
    bind_reader(monkeypatch, counts, reader)
    result = counts._totals()
    assert result["total"] == 30
    assert all("approval" not in sql and "project_status" not in sql for sql, _ in reader.calls)


def test_filter_count_uses_same_where_as_list():
    reader = Reader([[{"total": 7}]])
    query = ListQuery(project_status="1", purchaser_provname=["北京"])
    assert records.count_records(reader, "winbid", query) == 7
    where, params = records.where_clause(query)
    assert where in reader.calls[0][0]
    assert reader.calls[0][1] == params


def test_daily_uses_collect_date_and_status_one():
    reader = Reader([[]])
    statistics.daily(reader, "winbid", date(2026, 11, 12))
    sql, params = reader.calls[0]
    assert "project_status = '1'" in sql
    assert params == ("2026-11-12",)


@pytest.mark.parametrize("dates", [("2026-11-12", "2026-11-01"), ("2026-10-01", "2026-11-12")])
def test_stats_range_is_bounded(dates):
    with pytest.raises(ValidationError):
        StatsQuery(date_from=dates[0], date_to=dates[1])


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE x SET y=1",
        "DELETE FROM x",
        "INSERT INTO x VALUES (1)",
        "ALTER TABLE x ADD y INT",
        "DROP TABLE x",
        "SELECT 1; DELETE FROM x",
    ],
)
def test_reader_rejects_writes_before_cursor_is_opened(sql):
    connection = MagicMock()
    with pytest.raises(ValueError):
        source.Reader(connection).select(sql)
    connection.cursor.assert_not_called()


def test_reader_binds_and_closes_without_committing(monkeypatch):
    settings = Settings(mysql_host="example.invalid")
    monkeypatch.setattr(source, "get_settings", lambda: settings)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchall.return_value = [{"ready": 1}]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(source.pymysql, "connect", connect)
    assert source._ready()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()
    assert connect.call_args.kwargs["autocommit"] is True


def test_source_unavailable_is_503(monkeypatch):
    monkeypatch.setattr(source, "get_settings", Settings)
    with pytest.raises(DependencyUnavailableError), source.source_reader():
        pass
    monkeypatch.setattr(source, "get_settings", lambda: Settings(mysql_host="example.invalid"))
    monkeypatch.setattr(source.pymysql, "connect", MagicMock(side_effect=pymysql.OperationalError(2003, "failed")))
    with pytest.raises(DependencyUnavailableError), source.source_reader():
        pass


def test_only_get_routes_and_resource_authorization():
    assert audit_routes(app) == []
    mapping = permission_map(app)
    assert len(mapping) == 12
    for route in iter_api_routes(app):
        if route.path.startswith("/api/"):
            assert route.methods == {"GET"}
    assert mapping["GET /api/v1/tender/purchaser/export"][:2] == ("tender.purchaser", "export")
    assert mapping["GET /api/v1/tender/winbid/export"][:2] == ("tender.winbid", "export")
    assert mapping["GET /api/v1/tender/winbid/{record_id}/content"][:2] == ("tender.winbid", "read")


def test_http_requires_authentication_and_refuses_mutations():
    with TestClient(app) as client:
        assert client.get("/api/v1/tender/winbid").status_code == 401
        assert client.post("/api/v1/tender/winbid", json={}).status_code == 405
        assert client.get("/health/live").status_code == 200


def test_production_rejects_unset_and_demo_secret():
    for secret in ["", "dev-only-secret"]:
        with pytest.raises(ValidationError):
            Settings(environment="production", iam_service_secret=secret)


def test_columns_match_business_types():
    assert "winbid" in columns("winbid") and "open_date" not in columns("winbid")
    assert "open_date" in columns("purchaser") and "winbid" not in columns("purchaser")
    assert "content" not in columns("purchaser")


def test_background_count_deduplicates_and_returns_ready(monkeypatch):
    from concurrent.futures import Future

    future = Future()
    executor = MagicMock()
    executor.submit.return_value = future
    monkeypatch.setattr(counts, "_executor", executor)
    counts._jobs.clear()

    def operation():
        return {"total": 9}

    assert counts.poll("key", operation)["state"] == "pending"
    assert counts.poll("key", operation)["state"] == "pending"
    executor.submit.assert_called_once()
    future.set_result({"state": "ready", "data": {"total": 9}, "message": ""})
    assert counts.poll("key", operation)["data"]["total"] == 9
    counts._jobs.clear()


def test_count_failures_are_terminal():
    def fail():
        raise DependencyUnavailableError()

    assert counts._run(fail)["state"] == "error"


def test_list_reads_one_extra_row_to_determine_next_page(monkeypatch):
    reader = Reader([[{"id": i} for i in range(21)]])
    bind_reader(monkeypatch, service, reader)
    result = service.list_records("winbid", ListQuery())
    assert len(result["items"]) == 20
    assert result["has_more"] is True
    assert len(reader.calls) == 1


def test_http_routes_validate_filters_and_return_envelopes(monkeypatch):
    # 逐条替换已标记的权限依赖，不接触真实 IAM。

    for route in iter_api_routes(app):
        if route.path.startswith("/api/"):
            for dependency in route.dependencies:
                app.dependency_overrides[dependency.dependency] = lambda: None
    monkeypatch.setattr(
        service, "list_records", lambda kind, query: {"items": [], "has_more": False, "page": query.page}
    )
    monkeypatch.setattr(service, "get_record", lambda *args: {"id": "123"})
    monkeypatch.setattr(service, "get_content", lambda *args: {"html": "<p>正文</p>"})
    monkeypatch.setattr(counts, "get_count", lambda *args: {"state": "ready", "data": {"total": 3}})
    monkeypatch.setattr(counts, "get_totals", lambda: {"state": "pending", "data": None})
    monkeypatch.setattr(stats, "get_statistics", lambda query: {"daily": []})
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/tender/purchaser?project_status=2").status_code == 422
            assert client.get("/api/v1/tender/purchaser?unknown=x").status_code == 422
            assert client.get("/api/v1/tender/purchaser?collect_date_from=bad").status_code == 422
            for path in [
                "/purchaser",
                "/winbid/123",
                "/winbid/123/content",
                "/winbid/count",
                "/statistics/totals",
                "/statistics?date_from=2026-11-12&date_to=2026-11-12",
            ]:
                response = client.get("/api/v1/tender" + path)
                assert response.status_code == 200, response.text
                assert response.json()["code"] == "OK"
    finally:
        app.dependency_overrides.clear()


def test_collect_date_range_routes_as_daily_values_not_cross_shard_range():
    sql, params = records.where_clause(ListQuery(collect_date_from="2026-11-10", collect_date_to="2026-11-12"))
    assert "collect_date IN (%s, %s, %s)" in sql
    assert params == ("0", "2026-11-10", "2026-11-11", "2026-11-12")
    sql, params = records.where_clause(ListQuery(collect_date_from="2026-11-12", collect_date_to="2026-11-12"))
    assert "collect_date = %s" in sql
    assert params == ("0", "2026-11-12")


def test_totals_keep_last_success_while_refreshing_or_failed(monkeypatch):
    snapshot = {"total": 42, "purchaser": 20, "winbid": 22, "as_of": "2026-11-12T13:00:00+08:00"}
    monkeypatch.setattr(counts, "_last_totals", None)
    result = {"state": "ready", "data": snapshot}
    monkeypatch.setattr(counts, "poll", lambda *args: result)
    assert counts.get_totals()["data"] == snapshot
    result = {"state": "pending", "data": None}
    assert counts.get_totals() == {"state": "pending", "data": snapshot}
    result = {"state": "error", "data": None, "message": "源库超时"}
    assert counts.get_totals()["data"] == snapshot
    assert counts.get_totals()["message"] == "源库超时"


def test_empty_source_body_reports_matched_but_empty(monkeypatch):
    reader = Reader([[{"id": 1, "project_content_id": "a" * 32, "collect_date": "2023-08-03"}], [{"html": ""}]])
    bind_reader(monkeypatch, service, reader)
    with pytest.raises(NotFoundError, match="已关联到源记录，但正文内容为空"):
        service.get_content("purchaser", "0", 1)


async def test_totals_warmup_submits_before_first_page_visit(monkeypatch):
    import asyncio

    from app import main

    called = []
    monkeypatch.setattr(main, "get_totals", lambda: called.append(True))

    async def stop_after_first(interval):
        assert interval == 30
        raise asyncio.CancelledError()

    monkeypatch.setattr(main.asyncio, "sleep", stop_after_first)
    with pytest.raises(asyncio.CancelledError):
        await main.warm_totals()
    assert called == [True]


async def test_export_records_writes_xlsx_without_content_and_enforces_limit(monkeypatch):
    from io import BytesIO

    from openpyxl import load_workbook
    from platform_common.errors import ApiError

    sample = {
        "id": 1001,
        "project_content_id": "abc123",
        "project_name": "测试招标项目",
        "project_code": "ZB-001",
        "purchaser_provname": "广东省",
        "purchaser_cityname": "深圳市",
        "purchaser_countyname": "南山区",
        "purchaser": "测试单位",
        "purchaser_address": "测试地址",
        "agency": "测试代理",
        "public_date": "2026-11-12",
        "from_url": "https://example.com",
        "first_indty_name": "数字政府",
        "second_indty_name": "",
        "third_indty_name": "",
        "first_scene_name": "",
        "second_scene_name": "",
        "third_scene_name": "",
        "project_status": "1",
        "is_supp_scene": 1,
        "collect_date": "2026-11-12",
        "create_time": "2026-11-12 10:00:00",
        "open_date": "2026-11-20",
        "end_date": "2026-11-25",
    }
    reader = Reader([[sample]])
    bind_reader(monkeypatch, service, reader)
    payload = await service.export_records("purchaser", ListQuery(project_status="1"))
    book = load_workbook(BytesIO(payload))
    sheet = book.active
    assert sheet is not None
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][0] == "项目名称"
    assert "正文" not in rows[0]
    assert rows[1][0] == "测试招标项目"
    assert "人工已处理（信息化）" in rows[1]
    assert "已补充" in rows[1]

    monkeypatch.setattr(service.get_settings(), "export_max_rows", 1)
    too_many = Reader([[sample, {**sample, "id": 1002}]])
    bind_reader(monkeypatch, service, too_many)
    with pytest.raises(ApiError, match="超过单次导出上限"):
        await service.export_records("purchaser", ListQuery())
