"""政策解读输出字段映射常量，政策表导入与 AI 打标领域共用。"""

from __future__ import annotations

SOURCE_ID = "源ID"

ANSWER_FIELDS: dict[str, str] = {
    "政策要文": "policy_summary",
    "政策概览": "policy_summary",
    "一级行业": "industry_l1",
    "二级行业": "industry_l2",
    "三级行业": "industry_l3",
    "一级场景": "scenario_l1_name",
    "二级场景": "scenario_l2_name",
    "三级场景": "scenario_l3_name",
    "机会类型": "opportunity_type",
    "有无政府补贴": "has_subsidy",
    "补贴内容": "subsidy_content",
    "目标客户": "target_customers",
    "适配产品": "adapted_products",
    "目标客户采买理由": "purchase_reason",
    "是否新增场景": "is_new_scenario",
    "新增场景级别": "new_scenario_level",
    "信息化等级（高中低）": "info_level",
    "信息化等级": "info_level",
    "备注": "remark",
}
EXTRA_INTERPRET_ALIASES: dict[str, str] = {
    "行业": "industry_l1",
    "场景": "scenario_l1_name",
    "一级场景名称": "scenario_l1_name",
    "二级场景名称": "scenario_l2_name",
    "三级场景名称": "scenario_l3_name",
    "采买理由": "purchase_reason",
    "客户群": "target_customers",
    "政策市场机会": "market_opportunity",
    "市场机会": "market_opportunity",
}
KNOWN_INTERPRET_KEYS = {
    SOURCE_ID,
    *ANSWER_FIELDS,
    *EXTRA_INTERPRET_ALIASES,
    "行业场景",
    "省/直辖市",
    "省份",
}
