"""容器健康检查：leader 心跳在 60 秒内更新过才算健康。只有一个进程能拿到锁，备用进程会一直报不健康。"""

import asyncio
from datetime import timedelta

from platform_common.clock import utcnow

from app.core.database import SessionLocal, engine
from app.domain.models import WorkerHeartbeat

STALE = timedelta(seconds=60)


async def main() -> None:
    async with SessionLocal() as session:
        row = await session.get(WorkerHeartbeat, 1)
        healthy = row is not None and utcnow() - row.seen_at < STALE
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
