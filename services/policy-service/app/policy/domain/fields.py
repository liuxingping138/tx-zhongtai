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
    ColumnSpec("site_type", "网站类型", searchable=True),
    ColumnSpec("crawler_status", "爬虫状态", searchable=True),
    ColumnSpec("online_date", "上线时间"),
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
    ColumnSpec("adapted_products", "适配产品"),
    ColumnSpec("purchase_reason", "目标客户采买理由"),
    ColumnSpec("relation_key", "关联主键"),
    ColumnSpec("opportunity_type", "机会类型", searchable=True),
    ColumnSpec("policy_summary", "政策要文"),
    ColumnSpec("has_subsidy", "有无政府补贴"),
    ColumnSpec("subsidy_content", "补贴内容"),
    ColumnSpec("market_opportunity", "政策市场机会"),
    ColumnSpec("info_level", "信息化等级"),
    ColumnSpec("is_new_scenario", "是否新增场景"),
    ColumnSpec("new_scenario_level", "新增场景级别"),
    ColumnSpec("remark", "备注"),
    ColumnSpec("data_status", "数据状态"),
)

# 信源的爬虫状态。改成「已爬」记当天上线；「异常」由人工标，规则表同步（app.crawlconfig）只把未爬、没填的改成已爬。
CRAWLER_STATUS_ONLINE = "已爬"
CRAWLER_STATUS_ABNORMAL = "异常"
CRAWLER_STATUS_PENDING: tuple[str, ...] = ("", "未爬")

# 政策解读的数据状态：新录入、导入时默认待验证，人工核对后改为人工验证。
DATA_STATUS_PENDING = "待验证"
DATA_STATUS_VERIFIED = "人工验证"
DATA_STATUS_CHOICES: tuple[str, ...] = (DATA_STATUS_PENDING, DATA_STATUS_VERIFIED)

# AI 打标失败时写进基础标签备注的说明开头（app.aitag 写），基础标签列表的「打标状态」按它筛出要重打的政策。
AI_NOTE_TYPE_FAILED = "AI 类型判断失败"
AI_NOTE_TYPE_UNKNOWN = "AI 返回的类型不在码表里"
AI_NOTE_TYPE_EMPTY = "AI 没有判断出政策类型"
AI_NOTE_INTERPRET_FAILED = "AI 解读失败"
AI_NOTE_OPPORTUNITY_FAILED = "AI 市场机会失败"
AI_STATUS_CHOICES: tuple[str, ...] = (
    "类型判断失败",
    "解读失败",
    "市场机会失败",
    "等待重新判断类型",
    "待解读",
    "待补市场机会",
)
