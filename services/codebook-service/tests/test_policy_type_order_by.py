"""政策类型排序不能对 seq_no 裸强转整数。

seq_no 是用户可写的自由文本（API 的 seq_no 字段、Excel 的「序号」列都不限格式）。
原来 ORDER BY 直接 CAST(nullif(seq_no,'') AS INTEGER)，只要有一行填了「A1」，
列表和导出就永久 500，页面打不开、用户无法自行改回来。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.domain.models import PolicyType
from app.repositories.policy_types import ORDER_BY


def _order_by_sql() -> str:
    stmt = select(PolicyType.id).order_by(*ORDER_BY)
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled).replace("\n", " ")


def test_numeric_cast_is_guarded_by_digit_check() -> None:
    sql = _order_by_sql()
    assert "CAST" in sql, "序号仍应按数值排序"
    assert "^[0-9]+$" in sql, "强转前必须先判断是否纯数字，否则非数字取值会让整表查询报错"


def test_cast_is_not_applied_unconditionally() -> None:
    """裸 CAST 的特征是 order by 第一项直接是 CAST(...)，没有 CASE 包裹。"""

    sql = _order_by_sql()
    order_clause = sql.split("ORDER BY", 1)[1]
    assert "CASE" in order_clause
    assert order_clause.strip().startswith("CASE"), "数值强转必须在 CASE 的分支里"


def test_non_numeric_rows_sort_last_and_stay_deterministic() -> None:
    sql = _order_by_sql()
    order_clause = sql.split("ORDER BY", 1)[1]
    assert "NULLS LAST" in order_clause, "非数字序号应排在数字后面"
    # 非数字之间要有稳定次序，否则分页会来回跳。
    assert "seq_no" in order_clause.split("NULLS LAST", 1)[1]
    assert "type_name" in order_clause


def test_long_numbers_do_not_overflow() -> None:
    """序号填「20261029001」这种 10 位以上的数字：转 INTEGER 会溢出、整页 500，要转 NUMERIC。"""

    sql = _order_by_sql()
    assert "AS NUMERIC" in sql and "AS INTEGER" not in sql
