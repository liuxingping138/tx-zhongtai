"""爬虫配置同步读规则表：只取网站编码，去空白去重，没填编码的行单独数出来。源库用替身。"""

from __future__ import annotations

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


def test_rule_codes_are_trimmed_deduplicated_and_blank_rows_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = [" 11010100001 ", "11010100001", None, "", "62120000004"]
    rows: list[dict[str, Any]] = [{"site_code": code} for code in codes]
    cursor = FakeCursor(rows)
    used: list[str] = []

    def connect(db: str) -> FakeConnection:
        used.append(db)
        return FakeConnection(cursor)

    monkeypatch.setattr(rules_source, "mysql_connect", connect)
    result = rules_source.read_rule_codes()
    assert used == ["crawler2021"]
    assert cursor.sql == "SELECT site_code FROM policy_rules_alls"
    assert (result.rows, result.codes, result.blank_rows) == (5, {"11010100001", "62120000004"}, 2)
