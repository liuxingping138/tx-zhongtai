"""多选筛选：同一字段内「或」，空值不参与过滤。"""

from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects import postgresql

from platform_common.filters import escape_like, filter_values, ilike_any, in_any

_table = Table("t", MetaData(), Column("name", String), Column("status", String))


def _sql(clause: object) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


def test_filter_values_normalizes_single_multi_and_empty() -> None:
    assert filter_values(None) == []
    assert filter_values("") == []
    assert filter_values(" 广东省 ") == ["广东省"]
    assert filter_values(["广东省", "", "海南省", "广东省", "  "]) == ["广东省", "海南省"]


def test_ilike_any_ors_every_value() -> None:
    sql = _sql(ilike_any(_table.c.name, ["广东", "海南"]))
    assert sql.count("ILIKE") == 2
    assert " OR " in sql
    assert "'%%广东%%'" in sql and "'%%海南%%'" in sql  # psycopg 字面量把 % 转义成 %%


def test_single_value_keeps_previous_behaviour() -> None:
    # 字面量渲染会把 ESCAPE 的反斜杠再转义一次。
    assert _sql(ilike_any(_table.c.name, "广东")) == r"t.name ILIKE '%%广东%%' ESCAPE '\\'"


def test_empty_selection_does_not_filter() -> None:
    assert ilike_any(_table.c.name, []) is None
    assert ilike_any(_table.c.name, None) is None
    assert in_any(_table.c.status, ["", " "]) is None


def test_in_any_is_exact() -> None:
    assert _sql(in_any(_table.c.status, ["stale", "watch"])) == "t.status IN ('stale', 'watch')"


def test_like_wildcards_in_input_match_literally() -> None:
    """输入 `_`、`%` 必须按字面匹配，否则 `_` 会命中所有非空值。"""

    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("c:\\x") == "c:\\\\x"
    sql = _sql(ilike_any(_table.c.name, ["_"]))
    assert r"'%%\\_%%'" in sql and "ESCAPE" in sql
