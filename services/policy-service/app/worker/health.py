import asyncio
from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal, engine
from app.domain.scheduler_models import SchedulerHeartbeat


async def main() -> None:
    async with SessionLocal() as session:
        row = await session.get(SchedulerHeartbeat, 1)
        healthy = row is not None and datetime.now(UTC) - row.seen_at < timedelta(seconds=60)
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
