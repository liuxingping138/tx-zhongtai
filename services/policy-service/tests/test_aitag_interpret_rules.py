from __future__ import annotations

from types import SimpleNamespace

from app.aitag.domain import interpret_rules as rules

ANSWER = {
    "政策概览": "【政策信息化要文】建设一网统管平台",
    "一级行业": "党政行业",
    "二级行业": "政务",
    "三级行业": "-",
    "一级场景": "数字政府",
    "二级场景": "一网统管",
    "三级场景": "",
    "机会类型": "TO_G",
    "目标客户": "市大数据局",
    "适配产品": "移动云",
    "目标客户采买理由": "考核要求",
    "是否新增场景": "是的，新增二级场景",
    "信息化等级（高中低）": "高",
}


def test_answer_fields_land_in_interpretation_columns() -> None:
    values = rules.interpretation_values(ANSWER)
    assert values["policy_summary"].startswith("【政策信息化要文】")  # 政策概览就是政策要文
    assert (values["industry_l3"], values["scenario_l3_name"]) == ("", "")  # 「-」当空
    assert (values["is_new_scenario"], values["info_level"], values["adapted_products"]) == ("是", "高", "移动云")
    assert rules.interpretation_values({"是否新增场景": "否", "信息化等级": "中"})["info_level"] == "中"
    assert rules.interpretation_values({"一级行业": "行" * 300})["industry_l1"] == "行" * 128


def test_relation_key_uses_names_until_the_scenario_has_a_code() -> None:
    values = rules.interpretation_values(ANSWER)
    assert rules.relation_key("c1", values) == "c1新:党政行业/政务//数字政府/一网统管/TO_G"
    coded = {**values, "industry_scenario_code": "01010300234569261000"}
    assert rules.relation_key("c1", coded) == "c101010300234569261000TO_G"


def test_opportunities_match_by_industry_and_scene_then_fall_back() -> None:
    rows = [
        {"industry_l1": "党政行业", "scenario_l1_name": "数字政府"},
        {"industry_l1": "党政行业", "scenario_l1_name": "智慧城市"},
        {"industry_l1": "教育行业", "scenario_l1_name": "智慧校园"},
    ]
    items = [
        {"行业": "党政行业", "场景": "数字政府", "市场机会": "机会A"},
        {"行业": "教育行业", "场景": "不存在的场景", "市场机会": "机会B"},
        {"行业": "医卫行业", "场景": "智慧医院", "市场机会": "机会C"},
        {"行业": "党政行业", "场景": "数字政府", "市场机会": "-"},
    ]
    # 精确对上 -> 行 0；场景对不上退到同一级行业 -> 行 2；行业也对不上的丢掉；空机会忽略。
    assert rules.match_opportunities(items, rows) == {0: "机会A", 2: "机会B"}
    # 只给了一段又哪都对不上：整条政策的行都用它。
    assert rules.match_opportunities([{"行业": "x", "场景": "y", "市场机会": "整体机会"}], rows) == {
        0: "整体机会",
        1: "整体机会",
        2: "整体机会",
    }


def test_opportunity_prompt_lists_the_interpreted_scenes_once() -> None:
    base = {"源ID": "c1", "政策标题": "t"}
    rows = [{"industry_l1": "党政行业", "scenario_l1_name": "数字政府"}] * 2
    assert rules.opportunity_prompt_row(base, rows)["行业场景"] == "党政行业/数字政府"


def test_later_steps_reuse_the_first_step_column_names() -> None:
    tag = SimpleNamespace(
        source_content_id="c1",
        policy_name="方案",
        province_name="北京市",
        city_name="北京市",
        issued_at="2026-09-30",
        issuing_dept="市数据局",
        policy_level="地市级",
    )
    row = rules.base_prompt_row(tag, "正文")
    assert (row["源ID"], row["政策标题"], row["政策正文"], row["发文部门"]) == ("c1", "方案", "正文", "市数据局")


def test_codebook_paths_pasted_into_one_field_are_split_into_levels() -> None:
    # 码表把层级连写成「a > b > c」，模型偶尔整串填进一级字段。
    values = rules.interpretation_values(
        {
            "一级行业": "交通行业 > 交通运输、仓储和邮政业 > 多式联运和运输代理业",
            "一级场景": "低空经济＞低空物流配送",
            "三级场景": "无人机货运",
        }
    )
    assert rules.scenario_names(values) == (
        "交通行业",
        "交通运输、仓储和邮政业",
        "多式联运和运输代理业",
        "低空经济",
        "低空物流配送",
        "无人机货运",  # 路径只到二级，三级保留模型自己填的
    )


def test_the_longest_path_wins_and_leftover_paths_are_cleared() -> None:
    values = rules.interpretation_values(
        {"一级场景": "低空经济", "三级场景": "低空经济 > 低空物流配送 > 无人机货运", "一级行业": "互联网行业一部"}
    )
    assert rules.scenario_names(values) == ("互联网行业一部", "", "", "低空经济", "低空物流配送", "无人机货运")
    short = rules.interpretation_values({"一级场景": "低空经济 > 低空物流配送", "三级场景": "云 > 存储"})
    assert rules.scenario_names(short)[3:] == ("低空经济", "低空物流配送", "")


def test_long_paths_are_split_before_columns_are_truncated() -> None:
    values = rules.interpretation_values({"一级行业": "行" * 100 + " > " + "业" * 100})
    assert (values["industry_l1"], values["industry_l2"]) == ("行" * 100, "业" * 100)
