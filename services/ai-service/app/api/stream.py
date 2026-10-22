"""流式接口单独一个前缀：网关对 /api/v1/ai/stream 不挂压缩和请求缓冲，否则回答会攒满才一次性下发。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AskBody, ChatBody, sse_response
from app.api.security import CategoryAccess, SecurityClass, classified, get_category_access, require_ai_permission
from app.application import asking
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai", tags=["ai-stream"])


@router.post("/stream/ask")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def ask(
    body: AskBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission("ai.prompts", "ask")),
) -> StreamingResponse:
    """试发：@【列名】替换成模板 Excel 第一行的值后提问。替换和校验都在推流前完成，出错照常返回 4xx。"""

    model, prompt = await asking.prepare_trial(
        session, access, content=body.content, model_id=body.model_id, prompt_id=body.prompt_id
    )
    return sse_response(asking.stream_answer(model, prompt, thinking=body.thinking, echo_prompt=True))


@router.post("/stream/chat")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def chat(
    body: ChatBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission("ai.chat", "chat")),
) -> StreamingResponse:
    """多轮对话：上下文由模型服务端按 previous_response_id 保存，本服务不存对话内容。"""

    model, message = await asking.prepare_chat(session, body.model_id, body.message)
    return sse_response(
        asking.stream_answer(model, message, thinking=body.thinking, previous_response_id=body.previous_response_id)
    )


@router.get("/chat/models")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def chat_models(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission("ai.chat", "chat")),
) -> JSONResponse:
    return success_json(await asking.available_models(session))
