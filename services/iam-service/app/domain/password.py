"""Argon2id 密码哈希与校验。"""

from __future__ import annotations

from anyio import CapacityLimiter, to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()
# Argon2 一次几十毫秒、占 64MB 内存。IAM 只有一个事件循环，还要接全平台每个请求的鉴权：
# 放在协程里算，一波并发登录就把鉴权卡住、全平台 503。放线程池，并限制同时算的个数，免得内存跟着并发涨。
_HASH_SLOTS = 4
_limiter: CapacityLimiter | None = None

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


def _slots() -> CapacityLimiter:
    global _limiter  # noqa: PLW0603  限流器要在事件循环里建，第一次用到时才建
    if _limiter is None:
        _limiter = CapacityLimiter(_HASH_SLOTS)
    return _limiter


async def hash_password_async(password: str) -> str:
    return await to_thread.run_sync(hash_password, password, limiter=_slots())


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await to_thread.run_sync(verify_password, password_hash, password, limiter=_slots())
