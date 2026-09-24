"""登录限流不能被大小写、空格或「自己登录一次」绕开。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from platform_common.errors import RateLimitedError

from app.core.rate_limit import LoginRateLimiter


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def get(self, key: str) -> int | None:
        return self.store.get(key)

    async def ttl(self, key: str) -> int:
        return 300 if key in self.store else -2

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, _seconds: int) -> None:
        return None

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


def _limiter(redis: _FakeRedis) -> LoginRateLimiter:
    settings = SimpleNamespace(login_max_failures=5, login_max_failures_per_ip=20, login_lockout_seconds=300)
    return LoginRateLimiter(redis, settings)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_case_and_whitespace_variants_share_one_account_counter() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    for variant in ("admin", "Admin", "ADMIN", " admin", "admin "):
        await limiter.record_failure(variant, f"10.0.0.{len(variant)}")
    with pytest.raises(RateLimitedError):
        await limiter.assert_allowed("aDmIn", "10.0.0.99")


@pytest.mark.asyncio
async def test_successful_login_does_not_reset_ip_counter() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    for index in range(20):
        await limiter.record_failure(f"victim{index}", "10.0.0.1")
        if index % 4 == 3:
            # 攻击者穿插用自己的账号登录成功，试图把 IP 计数清零。
            await limiter.clear("attacker", "10.0.0.1")
    with pytest.raises(RateLimitedError):
        await limiter.assert_allowed("someone-else", "10.0.0.1")


@pytest.mark.asyncio
async def test_ip_threshold_is_wider_than_account_threshold() -> None:
    """同一出口 IP 下几位同事各输错几次，不应互相锁住。"""

    redis = _FakeRedis()
    limiter = _limiter(redis)
    for user in ("zhangsan", "lisi", "wangwu"):
        for _ in range(4):
            await limiter.record_failure(user, "10.0.0.1")
    await limiter.assert_allowed("zhaoliu", "10.0.0.1")


@pytest.mark.asyncio
async def test_success_clears_account_counter() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    for _ in range(4):
        await limiter.record_failure("Admin", "10.0.0.1")
    await limiter.clear("admin", "10.0.0.1")
    assert "iam:login:user:admin" not in redis.store
    assert redis.store["iam:login:ip:10.0.0.1"] == 4
