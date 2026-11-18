"""知识库列定义与 Excel 表头映射（导出、导出未定义数据、上传知识标签）。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

KNOWLEDGE_EXPORT_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("file_name", "资料名称"),
    ColumnSpec("file_type", "文件类型"),
    ColumnSpec("operator_type", "运营商类型"),
    ColumnSpec("depart_affiliation", "部门归属"),
    ColumnSpec("industry_type", "行业类型"),
    ColumnSpec("app_scenario", "应用场景"),
    ColumnSpec("market_category", "市场类别"),
    ColumnSpec("product_type", "产品类型"),
    ColumnSpec("product_sub_type", "产品子类型"),
    ColumnSpec("prov_name", "省份"),
    ColumnSpec("data_time", "资料时间"),
    ColumnSpec("uploaded_at", "上传时间"),
    ColumnSpec("file_suffix", "文件后缀"),
    ColumnSpec("file_size_display", "文件大小"),
)

# 「导出未定义数据」与「上传知识标签」共用列定义，文件ID 用于精确回写标签。
UNDEFINED_TAG_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("id", "文件ID"),
    ColumnSpec("file_name", "资料名称"),
    ColumnSpec("file_type", "文件类型"),
    ColumnSpec("operator_type", "运营商类型"),
    ColumnSpec("depart_affiliation", "部门归属"),
    ColumnSpec("industry_type", "行业类型"),
    ColumnSpec("app_scenario", "应用场景"),
    ColumnSpec("market_category", "市场类别"),
    ColumnSpec("product_type", "产品类型"),
    ColumnSpec("product_sub_type", "产品子类型"),
    ColumnSpec("prov_name", "省份"),
    ColumnSpec("data_time", "资料时间"),
    ColumnSpec("file_suffix", "文件后缀"),
    ColumnSpec("uploaded_at", "上传时间"),
    ColumnSpec("remark", "备注"),
)

TAG_WRITABLE_FIELDS: tuple[str, ...] = (
    "file_type",
    "operator_type",
    "depart_affiliation",
    "industry_type",
    "app_scenario",
    "market_category",
    "product_type",
    "product_sub_type",
    "prov_name",
    "data_time",
    "remark",
)
