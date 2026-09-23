"""政策三张表与 Excel 表头的对应关系。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

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

HEALTH_STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "watch": "观察",
    "broken": "断爬",
    "never": "从未出数",
}

CRAWLER_TASK_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("province_name", "省份", searchable=True),
    ColumnSpec("city_name", "地市", searchable=True),
    ColumnSpec("site_name", "网站名称", searchable=True),
    ColumnSpec("site_code", "网站编码", searchable=True),
    ColumnSpec("tag", "标签", searchable=True),
    ColumnSpec("health_status_label", "健康状态"),
    ColumnSpec("last_collect_date", "最后采集日期"),
    ColumnSpec("stale_days", "停更天数"),
    ColumnSpec("count_7d", "近7天采集条数"),
    ColumnSpec("count_30d", "近30天采集条数"),
    ColumnSpec("count_90d", "近90天采集条数"),
    ColumnSpec("count_total", "统计窗口内累计条数"),
    ColumnSpec("in_rules_label", "爬虫规则是否仍配置"),
    ColumnSpec("source_url", "栏目源链接"),
)

CRAWLER_SITE_STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "watch": "关注",
    "stale": "停更",
}

CRAWLER_SITE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("site_name", "网站名称", searchable=True),
    ColumnSpec("province_name", "省份", searchable=True),
    ColumnSpec("city_name", "地市", searchable=True),
    ColumnSpec("total_rows", "数据总量"),
    ColumnSpec("last_created_at", "最新入库时间"),
    ColumnSpec("last_published_date", "最近发布时间"),
    ColumnSpec("stale_days", "停更天数"),
    ColumnSpec("status_label", "状态"),
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
