"""用户联系方式的校验，以及「待分配角色」「关键词」筛选。"""

from __future__ import annotations

import pytest
from platform_common.errors import ApiError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.application.user_fields import normalize_email, normalize_phone, validate_username
from app.domain.filters import UserFilters
from app.domain.models import User
from app.repositories.users import NO_ROLE, _apply_user_filters


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


def test_company_email_can_be_the_username_and_case_does_not_matter() -> None:
    assert validate_username("xiaoyu.Z@telelands.com") == "xiaoyu.z@telelands.com"
    with pytest.raises(ApiError, match="仅允许字母、数字、点、下划线、连字符和 @"):
        validate_username("zhang三@telelands.com")
    with pytest.raises(ApiError, match="字母开头"):
        validate_username("@telelands.com")


def test_phone_keeps_digits_only() -> None:
    assert normalize_phone("138 0013-1001") == "13800131001"
    assert normalize_phone("") == ""


@pytest.mark.parametrize("bad", ["1371234", "23800131001", "1380013100a"])
def test_phone_rejects_non_mobile(bad: str) -> None:
    with pytest.raises(ApiError, match="11 位手机号"):
        normalize_phone(bad)


def test_email_is_trimmed_and_checked() -> None:
    assert normalize_email("  a.b@example.com ") == "a.b@example.com"
    assert normalize_email("") == ""
    with pytest.raises(ApiError, match="邮箱"):
        normalize_email("not-an-email")


def test_no_role_filter_selects_users_without_any_role() -> None:
    sql = _sql(_apply_user_filters(select(User), UserFilters(role_id=[NO_ROLE])))
    assert "NOT IN (SELECT iam_user_roles.user_id" in sql


def test_no_role_combines_with_real_roles_as_or() -> None:
    role = "2b1f0a52-5c1e-4c55-9d7d-6b1c2f0b9a10"
    sql = _sql(_apply_user_filters(select(User), UserFilters(role_id=[role, NO_ROLE])))
    assert " OR " in sql
    assert "NOT IN" in sql and "iam_user_roles.role_id IN" in sql


def test_only_invalid_role_ids_match_nothing() -> None:
    sql = _sql(_apply_user_filters(select(User), UserFilters(role_id=["not-a-uuid"])))
    assert "false" in sql.lower()


def test_keyword_searches_name_phone_and_email() -> None:
    sql = _sql(_apply_user_filters(select(User), UserFilters(keyword=["138"])))
    for column in ("username", "display_name", "phone", "email"):
        assert f"iam_users.{column}" in sql
