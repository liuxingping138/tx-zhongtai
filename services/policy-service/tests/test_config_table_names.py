from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db"


@pytest.mark.parametrize("table", ["csys_policy_info_source_all", "crawler2021.policy_rules_alls_spider"])
def test_crawler_table_accepts_plain_identifiers(table: str) -> None:
    settings = Settings(database_url=DATABASE_URL, crawler_data_table=table)

    assert settings.crawler_data_table == table


@pytest.mark.parametrize(
    "table",
    ["t; DROP TABLE x", "t WHERE 1=1", "`t`", "a.b.c", "1abc", ""],
)
def test_crawler_table_rejects_anything_that_could_change_the_sql(table: str) -> None:
    # 表名会拼进 SQL（不能参数绑定），配置阶段就要拒绝。
    with pytest.raises(ValidationError):
        Settings(database_url=DATABASE_URL, crawler_data_table=table)
