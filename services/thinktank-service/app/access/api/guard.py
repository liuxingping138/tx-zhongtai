"""智库全部业务路由共用的网络准入依赖，在 main.py 挂到资料库、报告库、方案库、我的收藏上。"""

from __future__ import annotations

from fastapi import Depends, Request
from platform_common.http_utils import client_ip
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.application import gate
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

logger = get_logger(__name__)


async def require_trusted_network(
    request: Request,
    # 和路由共用同一个会话（同一请求内依赖有缓存），不另占连接；配置走依赖，单测可以覆盖。
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> None:
    """公司网络或有效白名单才放行；否则 403 + THINKTANK_NETWORK_DENIED。

    PDF 分段读取每一段都会经过这里：公司 IP 只比对内存里的配置，不查库；其他 IP 查一次没到期的白名单（几十行、走索引）。
    白名单到期或被删，下一个请求就拦住，不缓存。
    """

    decision = await gate.decide(session, settings, client_ip(request))
    if not decision.allowed:
        logger.warning("thinktank_network_denied", ip=decision.ip, path=request.url.path)
        raise gate.NetworkDeniedError(decision.ip)
