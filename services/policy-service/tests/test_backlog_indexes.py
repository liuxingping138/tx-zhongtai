"""打标待办、还没和码表比对的解读行，查询要用上各自的部分索引：条件和索引一字不差，常量直接写进 SQL。

几百万行时用不上部分索引就是整表扫描：任务调度页每 5 秒数一次待办，AI 每批写完都要找出还没比对的行。
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
    unclassified_interpretation,
)
from app.policy.repositories import base_tags
from app.policy.repositories import interpretations as interpretation_repo

VERSIONS = Path(__file__).parents[1] / "migrations" / "versions"
# 建部分索引的几步迁移，按先后：后一步删掉的（DROPPED）不再算
MIGRATIONS = ("f4a5b6c7d581_policy_backlog_indexes.py", "a2b3c4d5e6f9_scenario_candidates.py")


def _migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), VERSIONS / name)
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
        ("ix_policy_interpretations_unclassified", unclassified_interpretation, "policy_interpretations"),
    ],
)
def test_each_query_condition_is_word_for_word_its_partial_index(index: str, condition: Any, table: str) -> None:
    assert _condition_sql(condition(), table) == _where(_indexes()[index])


def _built() -> list[tuple[str, str, str, str, str]]:
    built: dict[str, tuple[str, str, str, str, str]] = {}
    for name in MIGRATIONS:
        module = _migration(name)
        for dropped in getattr(module, "DROPPED", ()):
            built.pop(dropped[0], None)
        built.update({spec[0]: spec for spec in module.INDEXES})
    return list(built.values())


def test_the_migrations_build_the_same_indexes_as_the_models() -> None:
    indexes = _indexes()
    for name, table, columns, where, comment in _built():
        index = indexes[name]
        assert index.table is not None and index.table.name == table
        assert ", ".join(column.name for column in index.columns) == columns
        assert (_where(index) if index.dialect_options["postgresql"]["where"] is not None else "") == where
        assert comment


def test_constants_are_sent_inline_so_generic_plans_still_use_the_partial_indexes() -> None:
    # 绑定参数（need_interpret = $1）在通用执行计划里证明不了落在部分索引里，会退回整表扫描。
    sql = _as_executed(select(BaseTag.id).where(awaiting_interpretation()))
    assert "need_interpret = '是'" in sql
    sql = _as_executed(select(Interpretation.id).where(unclassified_interpretation()))
    assert "scenario_state = ''" in sql


async def _scalar(session: Any, statement: Any, value: Any) -> Any:
    session.statements.append(statement)
    return value


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
    session.scalar = lambda statement: _scalar(session, statement, 3)  # type: ignore[method-assign]  # 新增场景候选单独数
    counts = await tagging.pending_counts(session)  # type: ignore[arg-type]
    assert counts == {"type": 2, "interpret": 5, "opportunity": 7, "scenario": 3}
    sql = _as_executed(session.statements[0])
    # 三个数各数各的，不用一条 count(*) FILTER 整表扫。
    assert "FILTER" not in sql and sql.count("count(*)") == 3
    assert "type_retag_at IS NOT NULL" in sql and "need_interpret = '是'" in sql and "opportunity_at IS NULL" in sql


async def test_unclassified_rows_and_the_status_filters_use_the_same_conditions() -> None:
    session = _Session(None)
    session.scalars = lambda: []  # type: ignore[method-assign]  # 只看发出去的 SQL
    assert await interpretation_repo.unclassified_rows(session, 10) == []  # type: ignore[arg-type]
    sql = _as_executed(session.statements[0])
    assert "scenario_state = ''" in sql and "SKIP LOCKED" in sql
    (waiting,) = base_tags._conditions({"ai_status": ["待解读"]})
    assert _condition_sql(waiting, "policy_base_tags") == _where(_indexes()["ix_policy_base_tags_interpret_backlog"])
