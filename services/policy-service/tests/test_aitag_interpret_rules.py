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


def test_opportunity_text_only_takes_answers_for_the_asked_group() -> None:
    def pick(items: list[dict[str, str]]) -> str:
        return rules.extract_opportunity_text(items, "党政行业", "数字政府")

    # 只回了一段：一次只问一组，就算没标、或名称写法不一样也是这组的。
    assert pick([{"市场机会": "聚焦数字政府建设"}]) == "聚焦数字政府建设"
    assert pick([{"行业": "党政", "场景": "数字政府建设", "市场机会": "改写了名称"}]) == "改写了名称"
    # 好几段：标着这组的优先；空机会忽略。
    exact = [
        {"行业": "交通行业", "场景": "车路云", "市场机会": "交通机会"},
        {"一级行业": "党政行业", "一级场景": "数字政府", "市场机会": "政务机会"},
        {"行业": "党政行业", "场景": "数字政府", "市场机会": "-"},
    ]
    assert pick(exact) == "政务机会"
    # 没标的、只标了对得上的一半也算这组的。
    assert pick([{"市场机会": "甲"}, {"行业": "党政行业", "市场机会": "乙"}]) == "甲\n\n乙"
    # 好几段都标着别的行业场景：取不到，不能把别的场景的机会抄到这一行。
    others = [
        {"行业": "交通行业", "场景": "车路云", "市场机会": "交通机会"},
        {"行业": "党政行业", "场景": "城市大脑", "市场机会": "城市机会"},
    ]
    assert pick(others) == ""
    assert pick([]) == "" and pick([{"市场机会": "无"}]) == ""


def test_opportunity_prompt_rows_one_per_interpreted_group() -> None:
    base = {"源ID": "c1", "政策标题": "t"}
    rows = [
        {"industry_l1": "党政行业", "scenario_l1_name": "数字政府"},
        {"industry_l1": "党政行业", "scenario_l1_name": "数字政府"},
        {"industry_l1": "交通行业", "scenario_l1_name": "车路云"},
        # 行业或场景空着的组不问：问了白花钱，也写不回哪一行。
        {"industry_l1": "", "scenario_l1_name": "车路云"},
        {"industry_l1": "教育行业", "scenario_l1_name": " "},
    ]
    expanded = rules.opportunity_prompt_rows(base, rows)
    assert [pair for pair, _ in expanded] == [("党政行业", "数字政府"), ("交通行业", "车路云")]
    assert (expanded[0][1]["一级行业"], expanded[0][1]["一级场景"], expanded[0][1]["行业场景"]) == (
        "党政行业",
        "数字政府",
        "党政行业/数字政府",
    )
    assert expanded[1][1]["源ID"] == "c1" and expanded[1][1]["政策标题"] == "t"


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


def test_new_marks_are_dropped_from_scenario_names() -> None:
    # 模型把「标识新增的是哪一级」写进了名称；哪级是新的看「新增场景级别」，名称里不留标记，否则会原样进码表。
    values = rules.interpretation_values(
        {"一级场景": "中医药数智化（新增）", "二级场景": "国际交流平台 (新增)", "三级场景": "【新增】算水协同"}
    )
    assert _scenarios(values) == ("中医药数智化", "国际交流平台", "算水协同")


def _scenarios(values: dict[str, str]) -> tuple[str, str, str]:
    return values["scenario_l1_name"], values["scenario_l2_name"], values["scenario_l3_name"]


def test_aliases_and_dynamic_ai_outputs_are_extracted_without_collision() -> None:
    item = {
        "行业": "党政行业",
        "场景": "数字政府",
        "客户群": "各级政数局",
        "采买理由": "省厅文件要求",
        "政策亮点": "专项资金5000万",
        "申报截止期": "2026-12-31",
        "空字段": "-",
    }
    values = rules.interpretation_values(item)
    assert values["industry_l1"] == "党政行业"
    assert values["scenario_l1_name"] == "数字政府"
    assert values["target_customers"] == "各级政数局"
    assert values["purchase_reason"] == "省厅文件要求"
    extra = rules.extract_ai_outputs(item)
    assert extra == {"政策亮点": "专项资金5000万", "申报截止期": "2026-12-31", "空字段": ""}
