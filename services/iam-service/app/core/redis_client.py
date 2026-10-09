"""Redis 客户端。用于登录限流与短期会话状态，不作为权限数据的唯一来源。"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def check_redis_ready() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:  # noqa: BLE001  就绪检查只需要布尔结果
        return False
