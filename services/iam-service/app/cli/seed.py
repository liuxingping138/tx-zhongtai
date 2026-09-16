"""同步资源清单。用法：uv run python -m app.cli.seed"""

from __future__ import annotations

import asyncio
import logging

from app.application.seed import sync_catalog
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iam.cli.seed")


async def main() -> None:
    async with SessionLocal() as session:
        stats = await sync_catalog(session)
        await session.commit()
    logger.info("catalog_synced resources=%s actions=%s menus=%s", stats["resources"], stats["actions"], stats["menus"])


if __name__ == "__main__":
    asyncio.run(main())
