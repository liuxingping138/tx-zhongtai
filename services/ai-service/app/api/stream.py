"""流式接口单独一个前缀：网关对 /api/v1/ai/stream 不挂压缩和请求缓冲，否则回答会攒满才一次性下发。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from platform_common.actors import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AskBody, sse_response
from app.api.security import CategoryAccess, SecurityClass, classified, get_category_access, require_ai_permission
from app.application import asking, billing
from app.core.database import get_db_session
from app.domain.models import CALL_TRIAL
from app.domain.templating import split_fields

router = APIRouter(prefix="/api/v1/ai", tags=["ai-stream"])


@router.post("/stream/ask")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def ask(
    body: AskBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission("ai.prompts", "ask")),
) -> StreamingResponse:
    """试发：@【列名】替换成测试样本所选那一行的值后提问。替换和校验都在推流前完成，出错照常返回 4xx。"""

    model, prompt = await asking.prepare_trial(
        session,
        access,
        content=body.content,
        model_id=body.model_id,
        prompt_id=body.prompt_id,
        row=body.row,
        code_table=body.code_table,
    )
    category = await asking.trial_category(session, access, body.prompt_id, body.category)
    return sse_response(
        asking.stream_answer(
            model,
            prompt,
            thinking=body.thinking,
            trial_fields=split_fields(body.output_fields),
            on_done=lambda tally: billing.record_call(CALL_TRIAL, model, tally, actor, category=category),
        )
    )
