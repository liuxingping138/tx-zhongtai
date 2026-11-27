from __future__ import annotations

from app.domain.catalog import ACTION_SPECS, MENU_SPECS, RESOURCE_SPECS, RETIRED_ACTIONS, RETIRED_RESOURCE_CODES
from app.domain.enums import GrantLevel


def test_unpublished_business_resources_have_no_actions() -> None:
    unpublished = {spec.code for spec in RESOURCE_SPECS if spec.service_code != "iam-service" and not spec.published}
    for spec in ACTION_SPECS:
        assert spec.resource_code not in unpublished


def test_area_codes_resolve_is_independent_action() -> None:
    actions = {(spec.resource_code, spec.action_code) for spec in ACTION_SPECS}
    assert ("codebook.area_codes", "resolve") in actions
    assert ("codebook.area_codes", "export") in actions


def test_codebook_resources_are_published() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["codebook.policy_types"].published is True
    assert by_code["codebook.scenarios"].published is True
    assert by_code["codebook.area_codes"].published is True
    assert by_code["policy.sources"].published is True
    assert by_code["policy.base_tags"].published is True
    assert by_code["policy.interpretations"].published is True
    assert by_code["policy.crawler_monitoring"].published is True
    assert by_code["policy.crawler_monitoring"].name == "爬虫监测"
    assert by_code["policy.crawler_config"].published is True
    assert by_code["policy.crawler_config"].service_code == "policy-service"
    assert by_code["system.roles"].name == "角色与权限"


def test_user_delete_is_a_full_action() -> None:
    actions = {(spec.resource_code, spec.action_code) for spec in ACTION_SPECS}
    assert ("system.users", "delete") in actions


def test_retired_resources_are_not_in_the_catalog() -> None:
    """下线的资源如果又出现在清单里，同步时会被建回来，又立刻被退役步骤删掉。"""

    codes = {spec.code for spec in RESOURCE_SPECS}
    assert not codes & set(RETIRED_RESOURCE_CODES)
    assert not {spec.resource_code for spec in ACTION_SPECS} & set(RETIRED_RESOURCE_CODES)
    assert not {spec.resource_code for spec in MENU_SPECS if spec.resource_code} & set(RETIRED_RESOURCE_CODES)


def test_ai_module_has_four_pages_three_template_categories_and_release_control() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["ai"].node_type == "directory" and by_code["ai"].parent_code is None
    assert [code for code, spec in by_code.items() if spec.parent_code == "ai"] == [
        "ai.prompts",
        "ai.batch_runs",
        "ai.models",
        "ai.category.policy",
        "ai.category.customer",
        "ai.category.tender",
        "ai.releases",
        "ai.billing",
    ]
    routes = {spec.route_name for spec in MENU_SPECS if spec.parent_code == "menu.ai"}
    assert routes == {"ai-prompts", "ai-batch-runs", "ai-models", "ai-billing"}


def test_template_category_needs_full_to_edit_and_has_no_menu() -> None:
    """模板类型是数据范围不是页面：查看档只能看，改模板、试发、运行都要完整档；ai-service 按 list 动作取档位。"""

    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    menu_resources = {spec.resource_code for spec in MENU_SPECS}
    for code in ("ai.category.policy", "ai.category.customer", "ai.category.tender"):
        assert (levels[(code, "list")], levels[(code, "update")]) == ("READ", "FULL")
        assert code not in menu_resources


def test_ai_actions_that_spend_money_need_the_right_tier() -> None:
    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    assert levels[("ai.prompts", "ask")] == "FULL"
    assert levels[("ai.batch_runs", "run")] == "FULL"
    # 模型配置决定单价和调用参数，改它等于改所有人的花费口径。
    assert levels[("ai.models", "update")] == "FULL"
    # 上线让模板进定时任务按真实数据花钱，必须是完整档，且不挂菜单（按钮在提问配置页）。
    assert levels[("ai.releases", "publish")] == "FULL"
    assert "ai.releases" not in {spec.resource_code for spec in MENU_SPECS}


def test_crawler_config_report_is_read_for_leaders_and_full_to_sync() -> None:
    """爬虫配置统计给领导看：查看、导出各一档，手动同步规则表要完整档。"""

    levels = {
        spec.action_code: spec.required_level for spec in ACTION_SPECS if spec.resource_code == "policy.crawler_config"
    }
    assert levels == {"list": GrantLevel.READ, "export": GrantLevel.EXPORT, "sync": GrantLevel.FULL}
    menu = {spec.code: spec for spec in MENU_SPECS}["menu.policy.crawler_config"]
    assert (menu.route_name, menu.parent_code, menu.enabled) == ("policy-crawler-config", "menu.policy", True)


def test_scenario_review_has_its_own_resource_and_the_old_sync_action_is_retired() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["policy.scenario_candidates"].published is True
    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    assert levels[("policy.scenario_candidates", "decide")] == GrantLevel.FULL
    assert levels[("policy.scenario_candidates", "list")] == GrantLevel.READ
    for retired in RETIRED_ACTIONS:
        assert retired not in levels  # 留在清单里会被建回来，又被退役步骤删掉


def test_codebook_has_dictionary_and_thinktank_directories() -> None:
    by_code = {spec.code: spec for spec in MENU_SPECS}
    assert by_code["menu.codebook.dictionary"].parent_code == "menu.codebook"
    assert by_code["menu.codebook.dictionary"].title == "数据字典"
    assert by_code["menu.codebook.thinktank"].parent_code == "menu.codebook"
    assert by_code["menu.codebook.thinktank"].title == "智库码表"
    dict_children = [spec.title for spec in MENU_SPECS if spec.parent_code == "menu.codebook.dictionary"]
    assert dict_children == ["政策类型码表", "行业场景码表", "省市区码表"]
    thinktank_menus = [spec for spec in MENU_SPECS if spec.parent_code == "menu.codebook.thinktank"]
    assert [(m.title, m.route_name, m.resource_code, m.sort_order) for m in thinktank_menus] == [
        ("文件类别码表", "codebook-thinktank-file-types", "codebook.thinktank_file_types", 521),
        ("客户部门归属码表", "codebook-thinktank-departments", "codebook.thinktank_departments", 522),
        ("行业类别码表", "codebook-thinktank-industries", "codebook.thinktank_industries", 523),
        ("产品类别码表", "codebook-thinktank-product-types", "codebook.thinktank_product_types", 524),
        ("省份码表", "codebook-thinktank-provinces", "codebook.thinktank_provinces", 525),
        ("市场类别码表", "codebook-thinktank-market-categories", "codebook.thinktank_market_categories", 526),
    ]
    res_by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    for idx, menu in enumerate(thinktank_menus, start=54):
        assert menu.resource_code is not None
        res = res_by_code[menu.resource_code]
        assert (res.parent_code, res.sort_order, res.published) == ("codebook", idx, True)
        assert levels[(res.code, "list")] == GrantLevel.READ
        assert levels[(res.code, "export")] == GrantLevel.EXPORT
        for write_action in ("create", "update", "delete", "import"):
            assert levels[(res.code, write_action)] == GrantLevel.FULL


def test_thinktank_catalog_has_knowledge_reports_proposals_favorites_and_scopes() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["thinktank"].published is True
    assert (by_code["thinktank.knowledge"].name, by_code["thinktank.knowledge"].sort_order) == ("资料库", 451)
    assert (by_code["thinktank.reports"].name, by_code["thinktank.reports"].sort_order) == ("报告库", 452)
    assert (by_code["thinktank.proposals"].name, by_code["thinktank.proposals"].sort_order) == ("方案库", 453)
    assert (by_code["thinktank.favorites"].name, by_code["thinktank.favorites"].sort_order) == ("我的收藏", 454)
    for code in ("thinktank.knowledge", "thinktank.reports", "thinktank.proposals", "thinktank.favorites"):
        assert by_code[code].published is True
        assert by_code[code].parent_code == "thinktank"
    assert by_code["thinktank.knowledge.file_type"].parent_code == "thinktank.knowledge"
    assert by_code["thinktank.knowledge.industry_type"].parent_code == "thinktank.knowledge"
    assert by_code["thinktank.file_type.product"].parent_code == "thinktank.knowledge.file_type"
    assert by_code["thinktank.industry_type.energy"].parent_code == "thinktank.knowledge.industry_type"

    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    for lib_code in ("thinktank.knowledge", "thinktank.reports", "thinktank.proposals"):
        for act in ("list", "read", "preview", "favorite"):
            assert levels[(lib_code, act)] == GrantLevel.READ
        for act in ("export", "export_undefined", "download"):
            assert levels[(lib_code, act)] == GrantLevel.EXPORT
        for act in ("create", "update", "upload_tags", "delete"):
            assert levels[(lib_code, act)] == GrantLevel.FULL
    assert levels[("thinktank.favorites", "list")] == GrantLevel.READ
    assert levels[("thinktank.favorites", "favorite")] == GrantLevel.READ

    menus = [spec for spec in MENU_SPECS if spec.parent_code == "menu.thinktank"]
    assert [(m.code, m.title, m.route_name, m.resource_code, m.sort_order) for m in menus] == [
        ("menu.thinktank.knowledge", "资料库", "thinktank-knowledge", "thinktank.knowledge", 451),
        ("menu.thinktank.reports", "报告库", "thinktank-reports", "thinktank.reports", 452),
        ("menu.thinktank.proposals", "方案库", "thinktank-proposals", "thinktank.proposals", 453),
        ("menu.thinktank.favorites", "我的收藏", "thinktank-favorites", "thinktank.favorites", 454),
    ]
