from __future__ import annotations

from app.domain.catalog import ACTION_SPECS, RESOURCE_SPECS


def test_unpublished_business_resources_have_no_actions() -> None:
    unpublished = {spec.code for spec in RESOURCE_SPECS if spec.service_code != "iam-service" and not spec.published}
    for spec in ACTION_SPECS:
        assert spec.resource_code not in unpublished


def test_codebook_resources_are_published() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert by_code["codebook.policy_types"].published is True
    assert by_code["codebook.scenarios"].published is True
    assert by_code["codebook.area_codes"].published is True
    assert by_code["policy.sources"].published is True
    assert by_code["policy.base_tags"].published is True
    assert by_code["policy.interpretations"].published is True
    assert by_code["policy.crawler_monitoring"].published is False
