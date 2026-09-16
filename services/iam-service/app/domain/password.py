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
