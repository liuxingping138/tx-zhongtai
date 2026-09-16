"""账号 + IP 双维度登录限流。Redis 不可用时登录返回 503，不静默关闭限流。"""

from __future__ import annotations

from platform_common.errors import DependencyUnavailableError, RateLimitedError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings


class LoginRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    def _keys(self, username: str, ip: str) -> tuple[str, str]:
        return f"iam:login:user:{username}", f"iam:login:ip:{ip}"

    async def assert_allowed(self, username: str, ip: str) -> None:
        user_key, ip_key = self._keys(username, ip)
        try:
            user_count = int(await self._redis.get(user_key) or 0)
            ip_count = int(await self._redis.get(ip_key) or 0)
            user_ttl = int(await self._redis.ttl(user_key) or 0)
            ip_ttl = int(await self._redis.ttl(ip_key) or 0)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

        limit = self._settings.login_max_failures
        if user_count >= limit or ip_count >= limit:
            retry_after = max(user_ttl, ip_ttl, 1)
            raise RateLimitedError(
                "登录失败次数过多，请稍后重试",
                retry_after_seconds=retry_after,
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
        try:
            await self._redis.delete(*self._keys(username, ip))
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc
