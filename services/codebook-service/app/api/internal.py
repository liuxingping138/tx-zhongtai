"""服务间接口。网关不声明 /internal/ 前缀，外部访问不到；调用方按服务名和密钥核对。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from platform_common.internal_calls import verify_internal_caller
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SecurityClass, classified
from app.application import code_tables, scenario_sync
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


class ScenarioItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 每条：key（调用方用来对回结果）、三级行业名、三级场景名，可带 source_policy（来源政策名称，新建的场景记下它）。
    items: list[dict[str, Any]] = Field(max_length=5000)
    caller_name: str = Field(default="政策解读同步", max_length=100)


@router.post("/scenarios/lookup")
@classified(SecurityClass.INTERNAL)
async def lookup_scenarios(
    body: ScenarioItems,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """政策解读给非新增场景填编码：六级名称完全对上才有编码，只查不建。"""

    verify_internal_caller(request, settings.internal_caller_secrets)
    return success_json(await scenario_sync.lookup(session, body.items))


@router.post("/scenarios/sync")
@classified(SecurityClass.INTERNAL)
async def sync_scenarios(
    body: ScenarioItems,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """人工确认过的新增场景写进码表，按现有编码规则分配编码。同一场景重复同步返回原编码，不重复建。"""

    service = verify_internal_caller(request, settings.internal_caller_secrets)
    caller = Actor(id=service, name=body.caller_name)
    return success_json(await scenario_sync.sync(session, caller, body.items))
