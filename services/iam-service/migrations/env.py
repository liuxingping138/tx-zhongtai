"""IAM 数据库 Alembic 迁移环境。

连接串固定从 `IAM_DATABASE_URL` 环境变量读取，不使用启动时 `create_all`
替代迁移；`target_metadata` 引用 `app.core.database` 的声明式 Base，
P2 阶段加入领域模型后自动被 autogenerate 感知。
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from platform_common.orm_base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.domain import models as _iam_models  # noqa: F401  导入即注册模型到 Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    url = os.environ.get("IAM_DATABASE_URL")
    if not url:
        raise RuntimeError("环境变量 IAM_DATABASE_URL 未设置，迁移终止。")
    return url


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(get_database_url(), poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
