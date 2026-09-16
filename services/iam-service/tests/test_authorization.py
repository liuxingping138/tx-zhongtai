from __future__ import annotations

import uuid

from app.domain.authorization import (
    AuthzDecision,
    evaluate_authorization,
    max_level,
    remaining_loginable_superadmins,
)
from app.domain.enums import UserStatus


def test_merge_none_plus_read_is_read() -> None:
    assert max_level([None, "READ"]) == "READ"


def test_merge_read_plus_full_is_full() -> None:
    assert max_level(["READ", "FULL"]) == "FULL"


def test_disabled_role_equivalent_to_missing_grant() -> None:
    assert max_level([]) is None
    assert max_level(["NONE", None]) is None


def test_unpublished_and_unknown_denied() -> None:
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=False,
            action_required_level="READ",
            effective_level="FULL",
        )
        == AuthzDecision.DENY_UNPUBLISHED
    )
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=False,
            action_required_level=None,
            effective_level="FULL",
        )
        == AuthzDecision.DENY_UNPUBLISHED
    )
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=None,
            action_required_level="READ",
            effective_level="FULL",
        )
        == AuthzDecision.DENY_UNKNOWN
    )
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=True,
            action_required_level=None,
            effective_level="FULL",
        )
        == AuthzDecision.DENY_UNKNOWN
    )


def test_read_cannot_satisfy_full() -> None:
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=True,
            action_required_level="FULL",
            effective_level="READ",
        )
        == AuthzDecision.DENY_LEVEL
    )


def test_full_allows_read_action() -> None:
    assert (
        evaluate_authorization(
            account_active=True,
            resource_published=True,
            action_required_level="READ",
            effective_level="FULL",
        )
        == AuthzDecision.ALLOW
    )


def test_last_superadmin_cannot_be_removed() -> None:
    only = uuid.uuid4()
    other = uuid.uuid4()
    records = [(only, UserStatus.ACTIVE), (other, UserStatus.DISABLED)]
    assert remaining_loginable_superadmins(records, target_id=only, target_new_status=UserStatus.DISABLED) == 0
    assert remaining_loginable_superadmins(records, target_id=only, remove_role=True) == 0
    assert remaining_loginable_superadmins(records, target_id=other, target_new_status=UserStatus.DISABLED) == 1
