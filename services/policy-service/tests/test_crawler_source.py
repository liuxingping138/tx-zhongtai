"""爬虫库只读连接：只重试瞬时连接错误，且重试有上限。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

import pymysql
import pytest

from app.crawler.repositories import source as crawler_source


def test_transient_source_disconnect_reconnects_with_bounded_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep = MagicMock()
    monkeypatch.setattr(crawler_source.time, "sleep", sleep)
    operation = MagicMock(side_effect=[pymysql.err.OperationalError(2013, "lost"), 7])
    operation.__name__ = "read"
    assert crawler_source.retry_mysql_read(operation)() == 7
    assert operation.call_count == 2
    sleep.assert_called_once_with(1)


@pytest.mark.parametrize(("code", "attempts"), [(2013, 3), (1045, 1), (1064, 1)])
def test_source_retry_stops_and_does_not_retry_permanent_errors(
    monkeypatch: pytest.MonkeyPatch, code: int, attempts: int
) -> None:
    monkeypatch.setattr(crawler_source.time, "sleep", MagicMock())
    operation = MagicMock(side_effect=pymysql.err.OperationalError(code, "source failure"))
    operation.__name__ = "read"
    with pytest.raises(pymysql.err.OperationalError):
        crawler_source.retry_mysql_read(operation)()
    assert operation.call_count == attempts
