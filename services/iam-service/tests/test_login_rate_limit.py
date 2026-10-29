"""登录限流不能被大小写、空格、并发或「自己登录一次」绕开，也不能留下永不过期的计数。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.rate_limit import LoginLockedError, LoginLockouts, LoginRateLimiter

USER_KEY = "iam:login:user:admin"
IP_KEY = "iam:login:ip:10.0.0.1"


class _FakeRedis:
    """每个命令之前让出一次事件循环，并发请求才会真的交错执行。没有过期时间的键 ttl 返回 -1。"""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: int, *, ex: int, nx: bool) -> bool:
        await asyncio.sleep(0)
        if nx and key in self.store:
            return False
        self.store[key], self.ttls[key] = value, ex
        return True

    async def incr(self, key: str) -> int:
        await asyncio.sleep(0)
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key: str) -> int:
        await asyncio.sleep(0)
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    async def ttl(self, key: str) -> int:
        await asyncio.sleep(0)
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.store.pop(key, None) is not None)
            self.ttls.pop(key, None)
        return removed

    async def mget(self, keys: list[str]) -> list[int | None]:
        return [self.store.get(key) for key in keys]


SETTINGS = SimpleNamespace(login_max_failures=5, login_max_failures_per_ip=20, login_lockout_seconds=300)


def _limiter(redis: _FakeRedis) -> LoginRateLimiter:
    return LoginRateLimiter(redis, SETTINGS)  # type: ignore[arg-type]


async def _fail(limiter: LoginRateLimiter, username: str, ip: str) -> None:
    """一次输错：占名额、验密码失败，名额留着。"""

    await limiter.reserve(username, ip)


@pytest.mark.asyncio
async def test_case_and_whitespace_variants_share_one_account_counter() -> None:
    limiter = _limiter(_FakeRedis())
    for variant in ("admin", "Admin", "ADMIN", " admin", "admin "):
        await _fail(limiter, variant, f"10.0.0.{len(variant)}")
    with pytest.raises(LoginLockedError) as caught:
        await limiter.reserve("aDmIn", "10.0.0.99")
    assert caught.value.by_ip is False


@pytest.mark.asyncio
async def test_a_burst_of_concurrent_logins_only_gets_the_allowed_number_of_tries() -> None:
    """原来先读次数、失败后才加一：同时发出的一波请求都读到「没超限」，200 个并发就真验 200 次密码。"""

    limiter = _limiter(_FakeRedis())
    results = await asyncio.gather(*(limiter.reserve("admin", "10.0.0.1") for _ in range(50)), return_exceptions=True)
    assert sum(1 for result in results if result is None) == 5
    assert all(isinstance(result, LoginLockedError) for result in results if result is not None)


@pytest.mark.asyncio
async def test_success_clears_the_account_and_gives_back_only_its_own_ip_try() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    for _ in range(4):
        await _fail(limiter, "Admin", "10.0.0.1")
    await limiter.reserve("admin", "10.0.0.1")
    await limiter.succeeded("admin", "10.0.0.1")
    assert USER_KEY not in redis.store
    assert redis.store[IP_KEY] == 4  # 不清零：攻击者用自己的账号登录一次不能把 IP 计数重置


@pytest.mark.asyncio
async def test_successful_logins_do_not_reset_the_ip_counter() -> None:
    limiter = _limiter(_FakeRedis())
    for index in range(20):
        await _fail(limiter, f"victim{index}", "10.0.0.1")
        if index % 4 == 3 and index < 19:
            await limiter.reserve("attacker", "10.0.0.1")
            await limiter.succeeded("attacker", "10.0.0.1")
    with pytest.raises(LoginLockedError) as caught:
        await limiter.reserve("someone-else", "10.0.0.1")
    assert caught.value.by_ip is True and "网络出口" in caught.value.message


@pytest.mark.asyncio
async def test_ip_threshold_is_wider_than_account_threshold() -> None:
    """同一出口 IP 下几位同事各输错几次，不应互相锁住。"""

    limiter = _limiter(_FakeRedis())
    for user in ("zhangsan", "lisi", "wangwu"):
        for _ in range(4):
            await _fail(limiter, user, "10.0.0.1")
    await limiter.reserve("zhaoliu", "10.0.0.1")


@pytest.mark.asyncio
async def test_attempts_on_a_locked_account_do_not_count_against_the_office_ip() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    for _ in range(5):
        await _fail(limiter, "admin", "10.0.0.1")
    for _ in range(30):
        with pytest.raises(LoginLockedError):
            await limiter.reserve("admin", "10.0.0.1")
    assert (redis.store[USER_KEY], redis.store[IP_KEY]) == (5, 5)
    await limiter.reserve("colleague", "10.0.0.1")


@pytest.mark.asyncio
async def test_counters_always_expire_and_old_permanent_ones_get_an_expiry() -> None:
    """原来加一、设过期分两步，中间出错就留下永不过期的计数：账号或整个出口被永久锁住。"""

    redis = _FakeRedis()
    limiter = _limiter(redis)
    await _fail(limiter, "admin", "10.0.0.1")
    assert redis.ttls[USER_KEY] == 300 and redis.ttls[IP_KEY] == 300
    redis.store["iam:login:user:old"] = 5  # 旧版本留下的、没有过期时间的计数
    with pytest.raises(LoginLockedError):
        await limiter.reserve("old", "10.0.0.2")
    assert redis.ttls["iam:login:user:old"] == 300


@pytest.mark.asyncio
async def test_release_gives_back_both_tries_without_leaving_negative_counters() -> None:
    redis = _FakeRedis()
    limiter = _limiter(redis)
    await limiter.reserve("admin", "10.0.0.1")
    await limiter.release("admin", "10.0.0.1")
    assert USER_KEY not in redis.store and IP_KEY not in redis.store


@pytest.mark.asyncio
async def test_locked_attempts_are_logged_once_per_window() -> None:
    limiter = _limiter(_FakeRedis())
    assert await limiter.first_notice("admin", "10.0.0.1", "locked_account", 300) is True
    assert await limiter.first_notice("Admin", "10.0.0.1", "locked_account", 300) is False
    assert await limiter.first_notice("admin", "10.0.0.1", "locked_ip", 300) is True


@pytest.mark.asyncio
async def test_lockouts_list_permanent_counters_and_unlock_ips() -> None:
    redis = _FakeRedis()
    redis.store["iam:login:user:old"] = 5
    lockouts = LoginLockouts(redis, SETTINGS)  # type: ignore[arg-type]
    assert await lockouts.remaining_seconds(["old"]) == {"old": 300}
    redis.store[IP_KEY] = 21
    assert await lockouts.unlock_ip("10.0.0.1") is True and IP_KEY not in redis.store
