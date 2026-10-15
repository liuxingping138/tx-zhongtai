from __future__ import annotations

from app.domain.catalog import ACTION_SPECS, MENU_SPECS, RESOURCE_SPECS, RETIRED_RESOURCE_CODES


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


def test_ai_module_is_a_top_level_directory_with_three_pages() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["ai"].node_type == "directory" and by_code["ai"].parent_code is None
    assert [code for code, spec in by_code.items() if spec.parent_code == "ai"] == [
        "ai.prompts",
        "ai.batch_runs",
        "ai.chat",
    ]
    routes = {spec.route_name for spec in MENU_SPECS if spec.parent_code == "menu.ai"}
    assert routes == {"ai-prompts", "ai-batch-runs", "ai-chat"}


def test_ai_actions_that_spend_money_need_the_right_tier() -> None:
    levels = {(spec.resource_code, spec.action_code): spec.required_level for spec in ACTION_SPECS}
    assert levels[("ai.prompts", "ask")] == "FULL"
    assert levels[("ai.batch_runs", "run")] == "FULL"
    assert levels[("ai.chat", "chat")] == "READ"
