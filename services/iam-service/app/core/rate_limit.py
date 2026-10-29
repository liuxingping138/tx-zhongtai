"""账号 + IP 双维度登录限流。Redis 不可用时登录返回 503，不静默关闭限流。

两个维度各管一件事：

- 账号维度防止对单个账号猜密码。键必须与认证时一样规范化（去空格、转小写），
  否则 `Admin`、`ADMIN`、` admin` 各有一份计数，锁定形同虚设。
- IP 维度防止同一来源轮换账号撒网。同一出口 IP 下可能有多位同事，阈值比账号维度宽；
  登录成功**不**清零 IP 计数，否则攻击者用自己的账号登录一次就能把计数重置。
"""

from __future__ import annotations

from platform_common.errors import DependencyUnavailableError, RateLimitedError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings


def login_key_username(username: str) -> str:
    """与 AuthService.normalize_username 保持一致。"""

    return username.strip().lower()


def user_lock_key(username: str) -> str:
    return f"iam:login:user:{login_key_username(username)}"


class LoginRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    def _keys(self, username: str, ip: str) -> tuple[str, str]:
        return user_lock_key(username), f"iam:login:ip:{ip}"

    async def assert_allowed(self, username: str, ip: str) -> None:
        user_key, ip_key = self._keys(username, ip)
        try:
            user_count = int(await self._redis.get(user_key) or 0)
            ip_count = int(await self._redis.get(ip_key) or 0)
            user_ttl = int(await self._redis.ttl(user_key) or 0)
            ip_ttl = int(await self._redis.ttl(ip_key) or 0)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

        blocked_ttls = []
        if user_count >= self._settings.login_max_failures:
            blocked_ttls.append(user_ttl)
        if ip_count >= self._settings.login_max_failures_per_ip:
            blocked_ttls.append(ip_ttl)
        if blocked_ttls:
            raise RateLimitedError(
                "登录失败次数过多，请稍后重试",
                retry_after_seconds=max(*blocked_ttls, 1),
            )

    async def record_failure(self, username: str, ip: str) -> None:
        user_key, ip_key = self._keys(username, ip)
        ttl = self._settings.login_lockout_seconds
        try:
            user_count = int(await self._redis.incr(user_key))
            if user_count == 1:
                await self._redis.expire(user_key, ttl)
            ip_count = int(await self._redis.incr(ip_key))
            if ip_count == 1:
                await self._redis.expire(ip_key, ttl)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

    async def clear(self, username: str, ip: str) -> None:
        """登录成功只清账号计数，IP 计数等它自然过期。"""

        user_key, _ip_key = self._keys(username, ip)
        try:
            await self._redis.delete(user_key)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc


class LoginLockouts:
    """管理端看「谁被锁了」和手动解锁。只管账号维度：IP 维度锁的是一个出口，不对应某个人。"""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    async def remaining_seconds(self, usernames: list[str]) -> dict[str, int]:
        """每个账号还要锁多少秒；没锁的不出现。Redis 不可用时当作都没锁，不拖垮用户列表。"""

        keys = [user_lock_key(name) for name in usernames]
        if not keys:
            return {}
        try:
            counts = await self._redis.mget(keys)
            locked = [
                (name, key)
                for name, key, count in zip(usernames, keys, counts, strict=True)
                if int(count or 0) >= self._settings.login_max_failures
            ]
            result: dict[str, int] = {}
            for name, key in locked:
                ttl = int(await self._redis.ttl(key) or 0)
                if ttl > 0:
                    result[name] = ttl
            return result
        except RedisError:
            return {}

    async def unlock(self, username: str) -> bool:
        try:
            return bool(await self._redis.delete(user_lock_key(username)))
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc
