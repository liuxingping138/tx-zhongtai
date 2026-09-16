"""创建初始超级管理员。

密码只从环境变量 ADMIN_PASSWORD 读取，不接受命令行参数，避免进入 shell 历史。
已存在同名管理员时不改写密码。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from app.application.admin_create import AdminCreateError, create_initial_admin
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iam.cli.admin_create")


async def main() -> int:
    username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME", "系统管理员")
    if not password:
        logger.error("缺少环境变量 ADMIN_PASSWORD")
        return 2
    async with SessionLocal() as session:
        try:
            user, created = await create_initial_admin(
                session, username=username, password=password, display_name=display_name
            )
            await session.commit()
        except AdminCreateError as exc:
            logger.error("admin_create_failed reason=%s", str(exc))
            return 1
    if created:
        logger.info("admin_created username=%s must_change_password=true", user.username)
    else:
        logger.info("admin_exists username=%s password_unchanged=true", user.username)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
