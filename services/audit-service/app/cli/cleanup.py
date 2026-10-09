"""受控清理到期审计事件。必须使用独立清理连接串。"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.cleanup import delete_expired, record_cleanup
from app.core.config import get_settings
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit.cli.cleanup")


async def main() -> None:
    settings = get_settings()
    cleanup_url = settings.cleanup_database_url or os.environ.get("AUDIT_CLEANUP_DATABASE_URL")
    if not cleanup_url:
        raise SystemExit("缺少 AUDIT_CLEANUP_DATABASE_URL，拒绝使用应用账号执行清理")
    if cleanup_url == settings.database_url:
        raise SystemExit("清理连接不能与应用连接相同")

    cleanup_engine = create_async_engine(cleanup_url, pool_pre_ping=True)
    cleanup_sessions = async_sessionmaker(cleanup_engine, expire_on_commit=False)
    try:
        async with cleanup_sessions() as cleanup_session:
            deleted = await delete_expired(cleanup_session, retention_days=settings.retention_days)
        async with SessionLocal() as app_session:
            await record_cleanup(
                app_session,
                deleted=deleted,
                retention_days=settings.retention_days,
                max_bytes=settings.max_event_bytes,
            )
    finally:
        await cleanup_engine.dispose()
    logger.info("audit_cleanup_done deleted=%s retention_days=%s", deleted, settings.retention_days)


if __name__ == "__main__":
    asyncio.run(main())
