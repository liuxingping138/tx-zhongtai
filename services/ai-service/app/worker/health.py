"""容器健康检查：leader 心跳在 60 秒内更新过才算健康。只有一个进程能拿到锁，备用进程会一直报不健康。"""

import asyncio

from app.application.batch_queue import worker_status
from app.core.database import SessionLocal, engine


async def main() -> None:
    async with SessionLocal() as session:
        healthy = (await worker_status(session))["online"]
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
