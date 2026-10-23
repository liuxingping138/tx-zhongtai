from __future__ import annotations

from app.domain.catalog import ACTION_SPECS, MENU_SPECS, RESOURCE_SPECS, RETIRED_RESOURCE_CODES
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


def test_ai_module_has_five_pages_three_template_categories_and_release_control() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["ai"].node_type == "directory" and by_code["ai"].parent_code is None
    assert [code for code, spec in by_code.items() if spec.parent_code == "ai"] == [
        "ai.prompts",
        "ai.batch_runs",
        "ai.chat",
        "ai.models",
        "ai.category.policy",
        "ai.category.customer",
        "ai.category.tender",
        "ai.releases",
        "ai.billing",
    ]
    routes = {spec.route_name for spec in MENU_SPECS if spec.parent_code == "menu.ai"}
    assert routes == {"ai-prompts", "ai-batch-runs", "ai-chat", "ai-models", "ai-billing"}


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
    assert levels[("ai.chat", "chat")] == "READ"
    # 上线让模板进定时任务按真实数据花钱，必须是完整档，且不挂菜单（按钮在提问配置页）。
    assert levels[("ai.releases", "publish")] == "FULL"
    assert "ai.releases" not in {spec.resource_code for spec in MENU_SPECS}


def test_crawler_config_report_is_read_for_leaders_and_full_to_sync() -> None:
    """周报给领导看：查看、导出各一档，手动同步规则表要完整档。"""

    levels = {
        spec.action_code: spec.required_level for spec in ACTION_SPECS if spec.resource_code == "policy.crawler_config"
    }
    assert levels == {"list": GrantLevel.READ, "export": GrantLevel.EXPORT, "sync": GrantLevel.FULL}
    menu = {spec.code: spec for spec in MENU_SPECS}["menu.policy.crawler_config"]
    assert (menu.route_name, menu.parent_code, menu.enabled) == ("policy-crawler-config", "menu.policy", True)
