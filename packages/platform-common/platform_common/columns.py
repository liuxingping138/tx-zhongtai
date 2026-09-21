"""业务字段与 Excel 表头的对应关系。

各业务服务在自己的 ``app/domain/fields.py`` 里声明具体的列清单，
这里只放跨服务共用的结构与匹配规则。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    field: str
    header: str
    searchable: bool = False


# 导出时统一追加的留痕列，六张业务表一致。
AUDIT_EXPORT_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("created_at", "入库时间"),
    ColumnSpec("created_by_name", "入库人"),
    ColumnSpec("updated_at", "更新时间"),
    ColumnSpec("updated_by_name", "操作人"),
)


def normalize_header(value: str) -> str:
    text = (value or "").replace("\n", " ").strip()
    if not text:
        return ""
    return text.split()[0]


def header_to_field(columns: tuple[ColumnSpec, ...], header: str) -> str | None:
    """把 Excel 表头映射到业务字段。

    先找完全相同的表头，找不到再按前缀匹配，并取**最长**的那个前缀。
    取最长而不是取第一个：当「省份」和「省份编码」同时存在时，
    按列顺序取第一个会把「省份编码」错配成「省份」。
    """

    raw = (header or "").replace("\n", " ").strip()
    short = normalize_header(raw)
    if not raw:
        return None
    exact = [spec for spec in columns if raw == spec.header or short == spec.header]
    if exact:
        return exact[0].field
    prefixed = [spec for spec in columns if raw.startswith(spec.header) or (short and short.startswith(spec.header))]
    if prefixed:
        prefixed.sort(key=lambda spec: len(spec.header), reverse=True)
        return prefixed[0].field
    return None
