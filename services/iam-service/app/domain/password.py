"""Argon2id 密码哈希与校验。"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


def validate_password_policy(password: str) -> str | None:
    """返回错误信息；通过则返回 None。不记录明文。"""

    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位"
    # 只查长度时 11111111 也能过。
    if not (any(ch.isalpha() for ch in password) and any(ch.isdigit() for ch in password)):
        return "密码要同时包含字母和数字"
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
