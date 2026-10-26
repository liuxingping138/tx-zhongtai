import asyncio

from app.core.database import engine
from app.worker.scheduler import runner


async def main() -> None:
    healthy = await runner.healthy()
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
