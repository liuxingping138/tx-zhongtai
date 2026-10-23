"""爬虫配置同步读规则表：每个网站编码取最早那条规则的创建日期，没填编码的行单独数出来。源库用替身。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from app.crawlconfig.repositories import rules_source


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.sql = sql

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_each_site_takes_the_creation_date_of_its_earliest_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, Any]] = [
        {"site_code": " 11010100001 ", "create_time": datetime(2026, 10, 23, 9, 30)},
        {"site_code": "11010100001", "create_time": datetime(2024, 10, 15, 17, 29)},  # 同一网站更早的栏目
        {"site_code": None, "create_time": datetime(2023, 12, 19, 14, 24)},
        {"site_code": "", "create_time": datetime(2023, 12, 19, 14, 24)},
        {"site_code": "62120000004", "create_time": "2026-10-16 10:00:00"},
    ]
    cursor = FakeCursor(rows)
    used: list[str] = []

    def connect(db: str) -> FakeConnection:
        used.append(db)
        return FakeConnection(cursor)

    monkeypatch.setattr(rules_source, "mysql_connect", connect)
    result = rules_source.read_rule_codes()
    assert used == ["crawler2021"]
    assert cursor.sql == "SELECT site_code, create_time FROM policy_rules_alls"
    assert result.first_dates == {"11010100001": date(2024, 10, 15), "62120000004": date(2026, 10, 16)}
    assert (result.rows, result.blank_rows, result.codes) == (5, 2, {"11010100001", "62120000004"})
