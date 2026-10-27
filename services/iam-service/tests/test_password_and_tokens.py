from __future__ import annotations

from app.domain.password import hash_password, validate_password_policy, verify_password
from app.domain.tokens import generate_refresh_token, hash_refresh_token


def test_password_hash_and_verify() -> None:
    hashed = hash_password("correct-horse-1")
    assert hashed != "correct-horse-1"
    assert verify_password(hashed, "correct-horse-1")
    assert not verify_password(hashed, "wrong-password")


def test_password_policy() -> None:
    assert validate_password_policy("short") is not None
    assert validate_password_policy("long-enough") is not None  # 没有数字
    assert validate_password_policy("11111111") is not None  # 没有字母
    assert validate_password_policy("long-enough1") is None


def test_refresh_token_hash_is_stable_and_not_raw() -> None:
    raw = generate_refresh_token()
    hashed = hash_refresh_token(raw)
    assert hashed == hash_refresh_token(raw)
    assert hashed != raw
    assert len(hashed) == 64
