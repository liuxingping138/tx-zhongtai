"""业务字段与 Excel 表头的对应关系。

各业务服务在自己的 ``app/domain/fields.py`` 里声明具体的列清单，
这里只放跨服务共用的结构与匹配规则。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect


@dataclass(frozen=True)
class ColumnSpec:
    field: str
    header: str
    searchable: bool = False


def string_lengths(model: type) -> dict[str, int]:
    """ORM 模型里每个定长文本列的上限。导入、新建前按它校验：超长的值撞到库里是 DataError，用户只看到 500。"""

    mapper: Any = inspect(model)
    return {column.key: length for column in mapper.columns if (length := getattr(column.type, "length", None))}


def overlong_reasons(values: Mapping[str, str], columns: Sequence[ColumnSpec], lengths: Mapping[str, int]) -> list[str]:
    """超过列宽的字段，按表头写成校验说明：「网站名称超过 255 字」。"""

    return [
        f"{spec.header}超过 {lengths[spec.field]} 字"
        for spec in columns
        if spec.field in lengths and len(values.get(spec.field) or "") > lengths[spec.field]
    ]


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
    exact = [spec for spec in columns if spec.header in (raw, short)]
    if exact:
        return exact[0].field
    prefixed = [spec for spec in columns if raw.startswith(spec.header) or (short and short.startswith(spec.header))]
    if prefixed:
        prefixed.sort(key=lambda spec: len(spec.header), reverse=True)
        return prefixed[0].field
    return None
