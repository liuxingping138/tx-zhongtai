"""数据库引擎与会话工厂。P2 阶段在此基础上补充领域模型与仓储实现。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from platform_common.database import create_service_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_service_engine(settings.database_url, service_name=settings.service_name)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# 请求事务之外另起的短事务（登录失败、越权被拒的留痕，在线用户的最近活跃）用单独的小连接池。
# 它们都是在请求自己还占着一条连接时再要一条：和请求共用一个池（5+10 条）的话，并发十几个这样的请求
# 就都占着一条、等第二条，整池互相等到超时（30 秒）；业务服务问授权 2 秒超时，全平台一起 503。
# 小池拿不到连接半秒就放弃，调用方要么忽略（最近活跃），要么只记日志（留痕），不拖住请求。
side_engine = create_service_engine(
    settings.database_url,
    service_name=f"{settings.service_name}-side",
    pool_size=2,
    max_overflow=3,
    pool_timeout=0.5,
    statement_timeout_ms=10_000,
    idle_in_transaction_timeout_ms=30_000,
    use_env_overrides=False,
)
SideSessionLocal = async_sessionmaker(side_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """路由里必须写 `Depends(get_db_session, scope="function")`：默认的 request 作用域在响应发出后才提交，
    提交失败（如并发撞唯一约束）时客户端已经收到成功响应。"""

    async with SessionLocal() as session:
        try:
            yield session
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
