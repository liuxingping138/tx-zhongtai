"""服务间接口。网关不声明 /internal/ 前缀，外部访问不到；调用方按服务名和密钥核对。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.errors import InternalCallerRejectedError
from platform_common.http_utils import success_json
from platform_common.internal_calls import verify_internal_caller
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SecurityClass, classified
from app.application import code_tables, scenario_enrich, scenario_sync
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/internal/v1", tags=["internal"])
# 往场景码表里写的只有政策解读同步：AI 服务也持有本服务的内部密钥（取系统码表），不能拿它建场景。
SCENARIO_WRITERS = frozenset({"policy-service"})


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
    # 页面上点「同步新增场景」的那个人：码表里新建的场景记他是入库人，审计也记他，不记成服务名。
    caller_id: str = Field(default="", max_length=64)


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


class ScenarioPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 每条：key、path（场景路径，最多三级）、industry_l1（这个场景出现过的一级行业）。
    items: list[dict[str, Any]] = Field(max_length=500)


@router.post("/scenarios/context")
@classified(SecurityClass.INTERNAL)
async def scenario_context(
    body: ScenarioPaths,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """新增场景审核看的码表上下文：同一上级下已有的场景、字面最像的已有场景。只读。"""

    verify_internal_caller(request, settings.internal_caller_secrets)
    return success_json(await scenario_sync.context(session, body.items))


class EnrichBacklog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=200, ge=1, le=2000)


class EnrichItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 每条：path（场景路径），desc_90、desc_130、desc_pest、level_desc（新增那一级的描述），没写出来的为空
    items: list[dict[str, Any]] = Field(max_length=2000)


@router.post("/scenarios/enrich-backlog")
@classified(SecurityClass.INTERNAL)
async def enrich_backlog(
    body: EnrichBacklog,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """待补描述的新增场景（按场景路径合并），带上上级描述和同级示例给 AI 参照。"""

    verify_internal_caller(request, settings.internal_caller_secrets)
    return success_json(await scenario_enrich.backlog(session, body.limit))


@router.get("/scenarios/enrich-count")
@classified(SecurityClass.INTERNAL)
async def enrich_count(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """待补描述的场景数，任务调度页的「数据进度」用。"""

    verify_internal_caller(request, settings.internal_caller_secrets)
    return success_json({"pending": await scenario_enrich.count(session, "待补充")})


@router.post("/scenarios/enrich")
@classified(SecurityClass.INTERNAL)
async def enrich_write(
    body: EnrichItems,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """AI 写好的描述写进去，改成待确认。"""

    service = verify_internal_caller(request, settings.internal_caller_secrets)
    if service not in SCENARIO_WRITERS:
        raise InternalCallerRejectedError(f"{service} 不能改场景码表")
    return success_json(await scenario_enrich.write(session, body.items))


class ScenarioRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: list[str] = Field(min_length=1, max_length=3)
    new_name: str = Field(min_length=1, max_length=255)
    dry_run: bool = False
    caller_name: str = Field(default="新增场景审核", max_length=100)
    caller_id: str = Field(default="", max_length=64)


@router.post("/scenarios/rename")
@classified(SecurityClass.INTERNAL)
async def rename_scenario(
    body: ScenarioRename,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """已有场景改名（各行业、各客群的行一起改，编码不变）。dry_run 只数会改多少行。"""

    service = verify_internal_caller(request, settings.internal_caller_secrets)
    if service not in SCENARIO_WRITERS:
        raise InternalCallerRejectedError(f"{service} 不能改场景码表")
    caller = Actor(id=body.caller_id or service, name=body.caller_name)
    return success_json(await scenario_sync.rename(session, caller, body.path, body.new_name, dry_run=body.dry_run))


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
    if service not in SCENARIO_WRITERS:
        raise InternalCallerRejectedError(f"{service} 不能往场景码表里写")
    caller = Actor(id=body.caller_id or service, name=body.caller_name)
    return success_json(await scenario_sync.sync(session, caller, body.items))
