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


def ip_lock_key(ip: str) -> str:
    return f"iam:login:ip:{ip}"


# Redis TTL 的返回值：键在但没有过期时间。
_NO_EXPIRY = -1


class LoginLockedError(RateLimitedError):
    """被限流拦下：by_ip 表示是这个出口 IP 被暂时限制（同一出口下的所有人都登不上），不是这个账号被锁。"""

    def __init__(self, *, by_ip: bool, retry_after_seconds: int) -> None:
        message = (
            "这个网络出口登录失败次数过多，已暂时限制，请稍后重试或联系管理员"
            if by_ip
            else "登录失败次数过多，请稍后重试"
        )
        super().__init__(message, retry_after_seconds=retry_after_seconds)
        self.by_ip = by_ip


class LoginRateLimiter:
    """先占名额再验密码：两个维度各加一，超了就退回并拒绝。

    原来是先读次数、验完密码失败了再加一：同时发出的一波请求都在第一次加一之前读到「没超限」，
    5 次上限形同虚设。加一是原子的，每个请求按自己加完后的值判断，一波并发只放过上限以内的几个。
    验成功退回 IP 维度那一下、清掉账号计数；验失败的那一下留着，就是失败次数。
    """

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    def _keys(self, username: str, ip: str) -> tuple[str, str]:
        return user_lock_key(username), ip_lock_key(ip)

    async def _bump(self, key: str) -> int:
        # 键不在时先建一个带过期的 0 再加一：原来加一、设过期分两步，中间出错就留下永不过期的计数，
        # 账号或整个出口 IP 被永久锁住。旧版本留下的没过期时间的键也在这里补上。
        ttl = self._settings.login_lockout_seconds
        await self._redis.set(key, 0, ex=ttl, nx=True)
        count = int(await self._redis.incr(key))
        if int(await self._redis.ttl(key)) == _NO_EXPIRY:
            await self._redis.expire(key, ttl)
        return count

    async def _refund(self, key: str) -> None:
        # 刚好过期又被 DECR 建出来的负数键直接删掉，不留没有过期时间的键。
        if int(await self._redis.decr(key)) <= 0:
            await self._redis.delete(key)

    async def reserve(self, username: str, ip: str) -> None:
        user_key, ip_key = self._keys(username, ip)
        try:
            user_count = await self._bump(user_key)
            ip_count = await self._bump(ip_key)
            locked_account = user_count > self._settings.login_max_failures
            locked_ip = ip_count > self._settings.login_max_failures_per_ip
            if not (locked_account or locked_ip):
                return
            # 被拦下的这次不算失败：锁着的账号有人一直试，不能顺带把同一出口的同事也锁住。
            await self._refund(user_key)
            await self._refund(ip_key)
            blocked = [user_key] if locked_account else []
            blocked += [ip_key] if locked_ip else []
            ttls = [int(await self._redis.ttl(key) or 0) for key in blocked]
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc
        raise LoginLockedError(by_ip=locked_ip and not locked_account, retry_after_seconds=max(*ttls, 1))

    async def release(self, username: str, ip: str) -> None:
        """占了名额却没走到验密码结果（库出错之类）：两个维度都退回，不算一次失败。"""

        user_key, ip_key = self._keys(username, ip)
        try:
            await self._refund(user_key)
            await self._refund(ip_key)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

    async def succeeded(self, username: str, ip: str) -> None:
        """登录成功：清掉账号计数；IP 维度只退回这一次，不清零，否则攻击者用自己的账号登录一次就能把计数重置。"""

        user_key, ip_key = self._keys(username, ip)
        try:
            await self._redis.delete(user_key)
            await self._refund(ip_key)
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

    async def first_notice(self, username: str, ip: str, reason: str, seconds: int) -> bool:
        """锁定期间的尝试只在每个锁定窗口里记一次登录日志：每次都记，匿名请求就能无限写库、拖慢真实审计。"""

        # 出口 IP 被限制时按 IP 记：键里带用户名的话，换个用户名就又记一条，匿名请求照样能无限写库。
        who = "" if reason == "locked_ip" else f"{login_key_username(username)}:"
        key = f"iam:login:notice:{reason}:{who}{ip}"
        try:
            return bool(await self._redis.set(key, 1, ex=max(seconds, 1), nx=True))
        except RedisError:
            return True


class LoginLockouts:
    """管理端看「谁被锁了」和手动解锁。列表只看账号维度（IP 维度锁的是一个出口，不对应某个人）；
    出口 IP 的限制在登录日志里看得到，超级管理员可以解除。"""

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
                elif ttl == _NO_EXPIRY:
                    # 旧版本留下的没有过期时间的计数：也是锁着的，列出来才能在页面上解锁。
                    result[name] = self._settings.login_lockout_seconds
            return result
        except RedisError:
            return {}

    async def unlock(self, username: str) -> bool:
        try:
            return bool(await self._redis.delete(user_lock_key(username)))
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc

    async def unlock_ip(self, ip: str) -> bool:
        """解除某个出口 IP 的登录限制。IP 维度锁的是一整个出口（可能是全公司），只给超级管理员。"""

        try:
            return bool(await self._redis.delete(ip_lock_key(ip)))
        except RedisError as exc:
            raise DependencyUnavailableError("登录限流组件暂时不可用，请稍后重试") from exc
