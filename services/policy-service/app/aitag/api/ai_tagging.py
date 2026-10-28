"""政策 AI 打标三个任务的设置和可选模板。挂在任务调度资源下：查看档看设置，完整档才能改设置。

执行和执行记录走任务调度的接口（每个任务是一个调度任务，编码 policy_ai_<任务>）；花费在 AI提问 → 费用账单 里看。
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application import retag, samples
from app.aitag.application import settings as service
from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/ai-tagging", tags=["政策AI打标"])
RESOURCE = "system.scheduler"
Task = Literal["type", "interpret", "opportunity"]


class RetagBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    step: Task


class TaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(default="", max_length=32)
    batch_size: int
    content_max_chars: int
    daily_cost_limit: str = Field(pattern=r"^\d{1,8}(\.\d{1,2})?$")
    # 只有类型判断有读取进度，其余任务传空串。
    cursor_date: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    version: int = Field(ge=1)


@router.get("/tasks")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_tasks(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """三个任务的设置、今天和本月已花、正在跑的进度。"""

    return success_json(await service.list_tasks(session))


@router.get("/templates")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_templates(_: Actor = Depends(require_policy_permission(RESOURCE, "list"))) -> JSONResponse:
    """可选的上线模板（政策类）。"""

    return success_json(await service.templates())


@router.put("/tasks/{task}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_task(
    task: Task,
    body: TaskBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_task(session, actor, task, body.model_dump()))


@router.post("/retag")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def request_retag(
    body: RetagBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission("policy.base_tags", "update")),
) -> JSONResponse:
    """基础标签列表上勾选政策重新打标：放回某个任务的待办，下次执行那个任务时处理。"""

    return success_json(await retag.request(session, actor, body.ids, body.step))


# 提示词模板页用：取的是政策数据，能看政策基础标签的人就能取，不需要任务调度权限。
# 接口只能挂本服务的资源（test_route_security_class），所以不用 AI 模块的模板权限。
TEMPLATE_RESOURCE = "policy.base_tags"


@router.get("/contract")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def contract(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(TEMPLATE_RESOURCE, "list")),
) -> JSONResponse:
    """三个打标任务各给模板哪些列（@【列名】能引用的）、要模板输出哪些字段、现在用的哪个模板。"""

    return success_json(await samples.contract(session))


@router.get("/samples")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def sample_rows(
    task: Task,
    day: date | None = Query(default=None, description="类型判断用：源政策的采集日期"),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(TEMPLATE_RESOURCE, "list")),
) -> JSONResponse:
    """从数据库取模板的测试数据，和正式打标交给模板的一模一样。前端再存成模板的测试 Excel。"""

    return success_json(await samples.samples(session, task, day, limit))
