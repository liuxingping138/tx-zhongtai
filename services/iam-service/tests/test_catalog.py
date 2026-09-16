from __future__ import annotations

from app.domain.catalog import ACTION_SPECS, RESOURCE_SPECS


def test_business_resources_are_unpublished() -> None:
    for spec in RESOURCE_SPECS:
        if spec.service_code != "iam-service":
            assert spec.published is False


def test_no_fictional_business_actions() -> None:
    resource_codes = {spec.resource_code for spec in ACTION_SPECS}
    assert all(code.startswith("system.") for code in resource_codes)
