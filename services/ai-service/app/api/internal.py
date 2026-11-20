"""服务间接口：政策服务定时打标用。网关不声明 /internal/ 前缀，外部访问不到；调用方按服务名和密钥核对。"""

from __future__ import annotations

import json
from typing import Any

import anyio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.http_utils import success_json
from platform_common.internal_calls import verify_internal_caller
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import classified
from app.application import pipeline_runs
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class PipelineRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(max_length=32)
    rows: list[dict[str, Any]]
    cost_limit: str | None = Field(default=None, max_length=20)
    # 审计和批量历史里显示的发起方，如「政策 AI 打标·手动」。
    caller_name: str = Field(default="定时任务", max_length=100)
    # 调用方上一批的任务ID：那批中断或失败后重读同一批数据时，已经答好、内容没变的行直接沿用，不再花钱重问。
    reuse_run_id: str = Field(default="", max_length=32)
    # 调用方预生成的幂等运行 ID（32 位十六进制）：用于避免超时重试时重复创建孤儿任务。
    client_run_id: str = Field(default="", max_length=32)


def _parse_pipeline_body(raw: bytes) -> PipelineRunBody:
    try:
        payload = json.loads(raw)
        return PipelineRunBody.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ApiError("流水线任务请求体无效", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc


def _caller(request: Request, settings: Settings) -> str:
    return verify_internal_caller(request, settings.internal_caller_secrets)


@router.get("/online-templates")
@classified(SecurityClass.INTERNAL)
async def online_templates(
    request: Request,
    category: str = Query(max_length=16),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    _caller(request, settings)
    return success_json(await pipeline_runs.online_templates(session, category))


@router.post("/pipeline-runs")
@classified(SecurityClass.INTERNAL)
async def create_run(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    service = _caller(request, settings)
    raw = await request.body()
    body = await anyio.to_thread.run_sync(_parse_pipeline_body, raw)
    caller = Actor(id=service, name=body.caller_name)
    return success_json(await pipeline_runs.create(session, caller, body.model_dump()), status_code=201)


@router.get("/pipeline-runs/{run_id}")
@classified(SecurityClass.INTERNAL)
async def get_run(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    service = _caller(request, settings)
    return success_json(await pipeline_runs.status(session, run_id, Actor(id=service, name="定时任务")))


@router.get("/pipeline-runs/{run_id}/results")
@classified(SecurityClass.INTERNAL)
async def run_results(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    _caller(request, settings)
    return success_json(await pipeline_runs.results(session, run_id))


@router.post("/pipeline-runs/{run_id}/stop")
@classified(SecurityClass.INTERNAL)
async def stop_run(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    service = _caller(request, settings)
    return success_json(await pipeline_runs.stop(session, Actor(id=service, name="定时任务"), run_id))
