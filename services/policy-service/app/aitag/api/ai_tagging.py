"""政策 AI 打标三个任务的设置和可选模板。挂在任务调度资源下：查看档看设置，完整档才能改设置。

执行和执行记录走任务调度的接口（每个任务是一个调度任务，编码 policy_ai_<任务>）；花费在 AI提问 → 费用账单 里看。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application import settings as service
from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/ai-tagging", tags=["政策AI打标"])
RESOURCE = "system.scheduler"
Task = Literal["type", "interpret", "opportunity"]


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
