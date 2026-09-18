"""政策三张表与 Excel 表头的对应关系。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    field: str
    header: str
    searchable: bool = False


SOURCE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("internal_id", "内部唯一id"),
    ColumnSpec("site_code", "网站编码", searchable=True),
    ColumnSpec("province_name", "省份", searchable=True),
    ColumnSpec("province_code", "省份编码"),
    ColumnSpec("city_name", "地市", searchable=True),
    ColumnSpec("city_code", "地市编码"),
    ColumnSpec("district_name", "区县"),
    ColumnSpec("district_code", "区县编码"),
    ColumnSpec("site_name", "网站名称", searchable=True),
    ColumnSpec("crawl_priority", "网站梳理和抓取的优先级"),
    ColumnSpec("url", "链接"),
    ColumnSpec("tag", "标签", searchable=True),
    ColumnSpec("data_type", "数据类型"),
    ColumnSpec("department", "所属部门"),
)

BASE_TAG_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("policy_name", "政策名称", searchable=True),
    ColumnSpec("issuing_dept", "出台部门"),
    ColumnSpec("issuer_industry", "发文机构行业"),
    ColumnSpec("policy_level", "政策层级"),
    ColumnSpec("province_code", "省份编码"),
    ColumnSpec("province_name", "省份名称", searchable=True),
    ColumnSpec("city_code", "地市编码"),
    ColumnSpec("city_name", "地市名称"),
    ColumnSpec("issued_at", "当前政策出台时间"),
    ColumnSpec("policy_types", "政策类型", searchable=True),
    ColumnSpec("source_url", "原始网站链接"),
    ColumnSpec("is_penetrate", "是否穿透", searchable=True),
    ColumnSpec("penetrate_words", "穿透词"),
    ColumnSpec("penetrate_score", "穿透词评分"),
    ColumnSpec("need_interpret", "是否解读", searchable=True),
    ColumnSpec("remark", "备注"),
)

INTERPRETATION_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("record_id", "自增或雪花算法"),
    ColumnSpec("tenant_id", "租户ID"),
    ColumnSpec("policy_uid", "政策唯一标识"),
    ColumnSpec("policy_title", "政策原文名称", searchable=True),
    ColumnSpec("industry_scenario_code", "行业场景编码", searchable=True),
    ColumnSpec("industry_code", "行业编码"),
    ColumnSpec("industry_l1", "一级行业", searchable=True),
    ColumnSpec("industry_l2", "二级行业"),
    ColumnSpec("industry_l3", "三级行业"),
    ColumnSpec("scenario_code", "场景编码"),
    ColumnSpec("scenario_l1_name", "一级场景名称"),
    ColumnSpec("scenario_l2_name", "二级场景名称"),
    ColumnSpec("scenario_l3_name", "三级场景名称"),
    ColumnSpec("target_customers", "目标客户当前政策影响客户群"),
    ColumnSpec("relation_key", "关联主键"),
    ColumnSpec("opportunity_type", "机会类型", searchable=True),
    ColumnSpec("policy_summary", "政策要文"),
    ColumnSpec("has_subsidy", "有无政府补贴"),
    ColumnSpec("subsidy_content", "补贴内容"),
    ColumnSpec("market_opportunity", "政策市场机会"),
    ColumnSpec("info_level", "信息化等级"),
    ColumnSpec("is_new_scenario", "是否新增场景"),
    ColumnSpec("new_scenario_level", "新增场景级别"),
)

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
