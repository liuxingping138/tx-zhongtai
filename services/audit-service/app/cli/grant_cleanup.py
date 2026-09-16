"""把 audit_events 的删除权授给清理账号，并收回应用账号的更新/删除权。"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit.cli.grant_cleanup")


async def main() -> None:
    settings = get_settings()
    cleanup_user = settings.cleanup_db_user
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleanup_user):
        raise SystemExit("清理账号名非法")
    async with engine.begin() as conn:
        exists = await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": cleanup_user})
        if exists.scalar_one_or_none() is None:
            raise SystemExit(f"清理账号 {cleanup_user} 不存在，请先执行 make provision-audit-cleanup")
        await conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{cleanup_user}"'))
        await conn.execute(text(f'GRANT SELECT, DELETE ON TABLE audit_events TO "{cleanup_user}"'))
        await conn.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_events FROM PUBLIC"))
        await conn.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_events FROM CURRENT_USER"))
        await conn.execute(text("GRANT SELECT, INSERT ON TABLE audit_events TO CURRENT_USER"))
    logger.info("cleanup_grants_applied user=%s", cleanup_user)


if __name__ == "__main__":
    asyncio.run(main())
