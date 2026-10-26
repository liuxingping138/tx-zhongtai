"""费用账单：所有模型调用（批量任务、定时打标、样本试跑、试发、多轮对话）按日期、模型、用途看花了多少。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SecurityClass, classified, require_ai_permission
from app.application import billing as service
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai/billing", tags=["ai-billing"])
RESOURCE = "ai.billing"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def daily(
    date_from: date = Query(..., description="开始日期（北京时间，含）"),
    date_to: date = Query(..., description="结束日期（北京时间，含）"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """每天、每个模型、每种用途的次数、token 和费用；页面据此汇总和画图。"""

    return success_json(await service.daily(session, date_from, date_to))
