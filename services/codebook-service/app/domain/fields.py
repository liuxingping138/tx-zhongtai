"""码表列与 Excel 表头的对应关系。表头按用户提供的两份 xlsx 对齐。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

POLICY_TYPE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("seq_no", "序号"),
    ColumnSpec("type_name", "政策类型", searchable=True),
    ColumnSpec("definition", "定义", searchable=True),
)

SCENARIO_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("industry_scenario_code", "行业场景编码", searchable=True),
    ColumnSpec("industry_code", "行业编码"),
    ColumnSpec("industry_l1", "项目一级行业", searchable=True),
    ColumnSpec("industry_l2", "项目二级行业"),
    ColumnSpec("industry_l3", "项目三级行业"),
    ColumnSpec("scenario_tag", "场景标签", searchable=True),
    ColumnSpec("scenario_level", "场景level"),
    ColumnSpec("scenario_type", "场景类型"),
    ColumnSpec("desc_90", "场景描述(90字)"),
    ColumnSpec("desc_130", "场景描述(130字)"),
    ColumnSpec("desc_pest", "场景描述(PEST总结)"),
    ColumnSpec("scenario_source", "场景来源"),
    ColumnSpec("scenario_hierarchy", "场景层级"),
    ColumnSpec("scenario_code", "场景编码"),
    ColumnSpec("scenario_l1_name", "项目一级场景名称"),
    ColumnSpec("scenario_l1_desc", "项目一级场景描述"),
    ColumnSpec("scenario_l2_name", "项目二级场景名称"),
    ColumnSpec("scenario_l2_desc", "项目二级场景描述"),
    ColumnSpec("scenario_l3_name", "项目三级场景名称"),
    ColumnSpec("scenario_l3_desc", "项目三级场景描述"),
    ColumnSpec("customer_group_name", "客群名称", searchable=True),
    ColumnSpec("customer_group_industry", "客群行业"),
    ColumnSpec("org_keywords", "机构及企业名称包含关键词"),
    ColumnSpec("scope_keywords", "经营范围包含"),
    ColumnSpec("customer_level", "客户等级"),
    ColumnSpec("customer_category", "客户类别"),
    ColumnSpec("product_l1_name", "项目一级产品名称"),
    ColumnSpec("product_l2_name", "项目二级产品名称"),
    ColumnSpec("branch_count", "下属分支机构数"),
    ColumnSpec("product_l1_sort", "一级产品排序（正序）"),
    ColumnSpec("product_l2_sort", "二级产品排序（正序）"),
)

AREA_CODE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("prov_id", "省份编码"),
    ColumnSpec("prov_name", "省份名称", searchable=True),
    ColumnSpec("city_id", "城市编码"),
    ColumnSpec("city_name", "城市名称", searchable=True),
    ColumnSpec("county_id", "区县编码"),
    ColumnSpec("county_name", "区县名称", searchable=True),
    ColumnSpec("alias_prov_name", "省份别名"),
    ColumnSpec("alias_city_name", "城市别名"),
    ColumnSpec("alias_county_name", "区县别名"),
    ColumnSpec("city_name_short", "城市简称"),
    ColumnSpec("county_name_short", "区县简称"),
)
