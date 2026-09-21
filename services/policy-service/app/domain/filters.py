"""列表与导出共用的筛选类型。"""

from __future__ import annotations

# 字段名 -> 筛选值。空值表示该条件不参与过滤。
# 列表接口和导出接口传同一个结构，保证两边筛选语义一致。
Filters = dict[str, str | None]
