"""服务间接口。网关不声明 /internal/ 前缀，外部访问不到；调用方按服务名和密钥核对。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from platform_common.http_utils import success_json
from platform_common.internal_calls import verify_internal_caller
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SecurityClass, classified
from app.application import code_tables
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/internal/v1", tags=["internal"])


@router.get("/code-tables/{name}")
@classified(SecurityClass.INTERNAL)
async def code_table(
    name: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """AI 模板引用系统码表：每次取最新内容，码表改了模板跟着变。"""

    verify_internal_caller(request, settings.internal_caller_secrets)
    return success_json(await code_tables.render(session, name))
