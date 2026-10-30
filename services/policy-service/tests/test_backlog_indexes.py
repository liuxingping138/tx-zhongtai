"""打标待办、待同步新增场景的查询要用上各自的部分索引：条件和索引一字不差，常量直接写进 SQL。

几百万行时用不上部分索引就是整表扫描：任务调度页每 5 秒数一次待办，解读列表每次打开都数一遍待同步。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import ColumnElement, Index, select
from sqlalchemy.dialects.postgresql import asyncpg, dialect

from app.aitag.repositories import tagging
from app.policy.domain.models import (
    BaseTag,
    Interpretation,
    awaiting_interpretation,
    awaiting_opportunity,
    unsynced_new_scenario,
)
from app.policy.repositories import base_tags
from app.policy.repositories import interpretations as interpretation_repo

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "f4a5b6c7d581_policy_backlog_indexes.py"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backlog_indexes", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _indexes() -> dict[str, Index]:
    tables = (BaseTag.__table__, Interpretation.__table__)
    return {index.name: index for table in tables for index in table.indexes if index.name}


def _where(index: Index) -> str:
    return str(index.dialect_options["postgresql"]["where"])


def _as_executed(statement: Any) -> str:
    """asyncpg 实际发出去的 SQL：literal_execute 的常量在执行时内联，其余仍是参数。"""

    return str(statement.compile(dialect=asyncpg.dialect(), compile_kwargs={"render_postcompile": True}))


def _condition_sql(condition: ColumnElement[bool], table: str) -> str:
    compiled = condition.compile(dialect=dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled).replace(f"{table}.", "")


@pytest.mark.parametrize(
    ("index", "condition", "table"),
    [
        ("ix_policy_base_tags_interpret_backlog", awaiting_interpretation, "policy_base_tags"),
        ("ix_policy_base_tags_opportunity_backlog", awaiting_opportunity, "policy_base_tags"),
        ("ix_policy_interpretations_unsynced_scenarios", unsynced_new_scenario, "policy_interpretations"),
    ],
)
def test_each_query_condition_is_word_for_word_its_partial_index(index: str, condition: Any, table: str) -> None:
    assert _condition_sql(condition(), table) == _where(_indexes()[index])


def test_the_migration_builds_the_same_indexes_as_the_models() -> None:
    indexes = _indexes()
    for name, table, columns, where, comment in _migration().INDEXES:
        index = indexes[name]
        assert index.table is not None and index.table.name == table
        assert ", ".join(column.name for column in index.columns) == columns
        assert (_where(index) if index.dialect_options["postgresql"]["where"] is not None else "") == where
        assert comment


def test_constants_are_sent_inline_so_generic_plans_still_use_the_partial_indexes() -> None:
    # 绑定参数（need_interpret = $1）在通用执行计划里证明不了落在部分索引里，会退回整表扫描。
    sql = _as_executed(select(BaseTag.id).where(awaiting_interpretation()))
    assert "need_interpret = '是'" in sql
    sql = _as_executed(select(Interpretation.id).where(unsynced_new_scenario()))
    assert "is_new_scenario = '是'" in sql and "data_status = '人工验证'" in sql


class _Session:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        return self

    async def scalar(self, statement: Any) -> Any:
        self.statements.append(statement)
        return self.reply

    def one(self) -> Any:
        return self.reply


async def test_pending_counts_count_each_backlog_on_its_own_index() -> None:
    session = _Session((2, 5, 7))
    assert await tagging.pending_counts(session) == {"type": 2, "interpret": 5, "opportunity": 7}  # type: ignore[arg-type]
    sql = _as_executed(session.statements[0])
    # 三个数各数各的，不用一条 count(*) FILTER 整表扫。
    assert "FILTER" not in sql and sql.count("count(*)") == 3
    assert "type_retag_at IS NOT NULL" in sql and "need_interpret = '是'" in sql and "opportunity_at IS NULL" in sql


async def test_unsynced_count_and_the_status_filters_use_the_same_conditions() -> None:
    session = _Session(4)
    assert await interpretation_repo.count_unsynced_new_scenarios(session) == 4  # type: ignore[arg-type]
    assert "data_status = '人工验证'" in _as_executed(session.statements[0])
    (waiting,) = base_tags._conditions({"ai_status": ["待解读"]})
    assert _condition_sql(waiting, "policy_base_tags") == _where(_indexes()["ix_policy_base_tags_interpret_backlog"])
