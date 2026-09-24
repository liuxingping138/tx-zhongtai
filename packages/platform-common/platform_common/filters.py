"""列表与导出共用的筛选类型。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, or_

# 筛选值：多选下拉提交多个值（`?province_name=甲&province_name=乙`），同一字段内是「或」，
# 不同字段之间是「且」。单个字符串等价于只选了一个值。
FilterValue = str | Sequence[str] | None

# 字段名 -> 筛选值。空值表示该条件不参与过滤。
# 列表接口和导出接口传同一个结构，保证两边筛选语义一致。
Filters = dict[str, FilterValue]


def filter_values(value: FilterValue | Any) -> list[str]:
    """把单值/多值统一成去空、去重、保序的字符串列表。"""

    if value is None:
        return []
    raw = [value] if isinstance(value, str) else list(value)
    out: list[str] = []
    for item in raw:
        text = str(item).strip() if item is not None else ""
        if text and text not in out:
            out.append(text)
    return out


LIKE_ESCAPE = "\\"


def escape_like(text: str) -> str:
    """转义 LIKE 通配符，让用户输入的 `%`、`_` 按字面匹配。

    不转义时输入 `_` 会命中所有非空值，输入 `100%` 会把 `100` 开头的都查出来。
    配合 ``column.ilike(..., escape=LIKE_ESCAPE)`` 使用。
    """

    return text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", "\\%").replace("_", "\\_")


def contains_ilike(column: Any, text: str) -> ColumnElement[bool]:
    """按字面包含匹配，忽略大小写。"""

    cond: ColumnElement[bool] = column.ilike(f"%{escape_like(text)}%", escape=LIKE_ESCAPE)
    return cond


def ilike_any(column: Any, value: FilterValue) -> ColumnElement[bool] | None:
    """多个值任一模糊命中即可；没有有效值时返回 None，表示不参与过滤。"""

    values = filter_values(value)
    if not values:
        return None
    return or_(*(contains_ilike(column, item) for item in values))


def in_any(column: Any, value: FilterValue) -> ColumnElement[bool] | None:
    """精确匹配任一值，用于状态这类枚举字段。"""

    values = filter_values(value)
    if not values:
        return None
    cond: ColumnElement[bool] = column.in_(values)
    return cond
