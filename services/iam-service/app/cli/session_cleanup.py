"""清理已过期/已撤销的会话与刷新令牌。

用法：make iam-session-cleanup
只删已失效且超过保留期的记录，不会影响在用会话。
"""

from __future__ import annotations

import asyncio
import logging

from app.application.session_cleanup import cleanup_sessions
from app.core.config import get_settings
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iam.cli.session_cleanup")


async def main() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        result = await cleanup_sessions(session, retention_days=settings.session_retention_days)
    logger.info(
        "iam_session_cleanup_done retention_days=%s tokens_deleted=%s sessions_deleted=%s "
        "tokens_remaining=%s sessions_remaining=%s",
        settings.session_retention_days,
        result.tokens_deleted,
        result.sessions_deleted,
        result.tokens_remaining,
        result.sessions_remaining,
    )


if __name__ == "__main__":
    asyncio.run(main())
