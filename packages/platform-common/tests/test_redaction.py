"""脱敏清单与递归行为。曾出现三份清单各自漂移、日志那份漏了 list 的情况。"""

from __future__ import annotations

from platform_common.logging_setup import _redaction_processor
from platform_common.redaction import REDACTED, SENSITIVE_KEYS, redact


def test_redacts_top_level_key() -> None:
    assert redact({"password": "x"})["password"] == REDACTED


def test_recurses_into_nested_dict() -> None:
    result = redact({"body": {"user": {"new_password": "x"}}})
    assert result["body"]["user"]["new_password"] == REDACTED


def test_recurses_into_list() -> None:
    """日志那份旧实现只递归 dict，藏在数组里的敏感键会原样输出。"""

    result = redact({"items": [{"access_token": "x"}, {"username": "amy"}]})
    assert result["items"][0]["access_token"] == REDACTED
    assert result["items"][1]["username"] == "amy"


def test_key_match_is_case_insensitive() -> None:
    assert redact({"Authorization": "Bearer x"})["Authorization"] == REDACTED


def test_keeps_business_fields() -> None:
    payload = {"actor_name": "amy", "count": 3, "changes": {"department": "研发部"}}
    assert redact(payload) == payload


def test_covers_keys_from_every_former_copy() -> None:
    """合并前三份清单的并集，任何一份的键都不能丢。"""

    for key in (
        "temporary_password",
        "password_hash",
        "internal_token",  # 原来只有 iam 那份有
        "csrf_token",
        "jwt",  # 原来只有日志那份有
        "id_token",
        "client_secret",
        "private_key",
        "set-cookie",
    ):
        assert key in SENSITIVE_KEYS, key


def test_logging_processor_uses_shared_list() -> None:
    event = {"event": "login", "password": "x", "extra": [{"secret": "y"}]}
    result = _redaction_processor(None, "info", event)
    assert result["password"] == REDACTED
    assert result["extra"][0]["secret"] == REDACTED
    assert result["event"] == "login"
