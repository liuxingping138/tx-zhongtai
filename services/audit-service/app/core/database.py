"""数据库引擎与会话工厂。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from platform_common.database import create_service_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_service_engine(settings.database_url, service_name=settings.service_name)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """路由里必须写 `Depends(get_db_session, scope="function")`：默认的 request 作用域在响应发出后才提交，
    提交失败（如并发撞唯一约束）时客户端已经收到成功响应。"""

    async with SessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001  就绪检查只需要布尔结果
        return False
