"""操作日志的「类型」列：AI 的审计事件早先没记模板类型，按事件目标（模板ID或任务ID）回本服务查。

审计记录只增不改，不回写；页面拿到一页事件后，把没带类型的 AI 事件的目标ID 一次性传来查。
权限跟操作日志走（system.audit 查看档）：看日志的人未必有 AI 模块的权限，这里只回类型编码，不回模板内容。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SecurityClass, classified, require_ai_permission
from app.application import audit_lookup as service
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai/audit-categories", tags=["ai-audit"])
MAX_IDS = 200


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def categories(
    ids: list[str] = Query(default=[], max_length=MAX_IDS, description="审计事件的目标ID（模板ID或任务ID）"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission("system.audit", "list")),
) -> JSONResponse:
    """{目标ID: 模板类型编码}，查不到的不出现。"""

    return success_json({"items": await service.categories(session, ids)})
