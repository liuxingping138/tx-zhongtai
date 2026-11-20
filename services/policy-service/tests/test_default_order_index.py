"""基础标签默认排序的索引不能直接建在 policy_name（Text）上：超长标题写不进 btree，整批打标、导入回滚。

列表的 ORDER BY 必须和索引表达式一字不差、截取长度直接写进 SQL，否则 PostgreSQL 用不上这个索引。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from sqlalchemy import Column, select
from sqlalchemy.dialects.postgresql import asyncpg, dialect

from app.policy.domain.models import DEFAULT_ORDER_NAME_CHARS, BaseTag, default_order
from app.policy.repositories import base_tags

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "b2c3d4e5f6a7_base_tag_default_order_bounded.py"
INDEX = "ix_policy_base_tags_default_order"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("default_order_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _model_columns() -> str:
    index = next(index for index in BaseTag.__table__.indexes if index.name == INDEX)
    parts = []
    for expression in index.expressions:
        if isinstance(expression, Column):
            parts.append(expression.name)
        else:
            parts.append(str(expression.compile(dialect=dialect())))
    return ", ".join(parts)


def test_the_index_never_holds_the_whole_policy_name() -> None:
    index = next(index for index in BaseTag.__table__.indexes if index.name == INDEX)
    assert "policy_name" not in [column.name for column in index.columns]
    assert _model_columns() == f"province_code, left(policy_name, {DEFAULT_ORDER_NAME_CHARS}), id"


def test_the_migration_builds_the_same_expression_as_the_model() -> None:
    module = _migration()
    assert module.down_revision == "b1c2d3e4f5a6"
    assert _model_columns() == module.COLUMNS


def test_the_list_order_matches_the_index_with_the_length_inline() -> None:
    assert base_tags._ORDER[-1] is BaseTag.id
    statement = select(BaseTag.id).order_by(*default_order())
    sql = str(statement.compile(dialect=asyncpg.dialect(), compile_kwargs={"render_postcompile": True}))
    assert f"left(policy_base_tags.policy_name, {DEFAULT_ORDER_NAME_CHARS})" in sql
    assert "$" not in sql.split("ORDER BY", 1)[1]
