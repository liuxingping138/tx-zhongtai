"""流式提问：提问配置页的试发、多轮对话。

返回 SSE 文本块：每块 `data: {json}\\n\\n`，最后一块 `data: [DONE]`。事件见 app.core.llm，另加：
    {"prompt": 实际发出的提示词}   试发时第一块，变量已替换成 Excel 第一行的值
    {"model": {...}}               本次使用的模型，前端据此算费用
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import anyio
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import run_excel_parse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.prompts import require
from app.application.sheets import read_sheet
from app.core import storage
from app.core.config import get_settings
from app.core.llm import LlmRequest, stream_responses
from app.domain.llm_models import MODELS, LlmModel, build_body, find_model
from app.domain.templating import CODE_TABLE_FIELD, fill_template, template_variables

MESSAGE_MAX = 200_000


def _sse(payload: dict[str, Any] | str) -> str:
    data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f"data: {data}\n\n"


def api_key_for(model: LlmModel) -> str:
    settings = get_settings()
    return settings.ark_api_key if model.provider == "ark" else settings.baidu_api_key


def model_info(model: LlmModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "name": model.name,
        "provider": model.provider_name,
        "web_search": model.web_search,
        "supports_thinking": model.supports_thinking,
        "available": bool(api_key_for(model)),
        "input_price": str(model.input_price),
        "output_price": str(model.output_price),
        "search_price": str(model.search_price),
    }


def available_models() -> list[dict[str, Any]]:
    return [model_info(model) for model in MODELS]


def resolve_model(model_id: str) -> LlmModel:
    model = find_model(model_id)
    if model is None:
        raise ApiError(f"未知模型：{model_id or '（未选择）'}", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not api_key_for(model):
        raise ApiError(
            f"{model.provider_name}的接口密钥未配置，暂不能使用该模型",
            http_status=503,
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        )
    return model


def llm_request(model: LlmModel, body: dict[str, Any]) -> LlmRequest:
    return LlmRequest(model.base_url, api_key_for(model), body, get_settings().llm_read_timeout_seconds)


def _check_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        raise ApiError("提问内容不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if len(text) > MESSAGE_MAX:
        raise ApiError("提问内容过长", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return text


async def _first_row_values(session: AsyncSession, prompt_id: str) -> dict[str, str]:
    """模板 Excel 第一条数据 + 码表全文，用来把 @【列名】@【上传码表】替换成真实值。"""

    template = await require(session, prompt_id)
    values: dict[str, str] = {}
    excel = storage.prompt_file(prompt_id, "excel")
    if template.excel_name and await anyio.Path(excel).is_file():
        _, rows = await run_excel_parse(
            lambda content: read_sheet(content, limit=1), await anyio.Path(excel).read_bytes()
        )
        values.update(rows[0] if rows else {})
    code = storage.prompt_file(prompt_id, "code")
    if template.code_name and await anyio.Path(code).is_file():
        values[CODE_TABLE_FIELD] = await anyio.Path(code).read_text(encoding="utf-8")
    return values


async def prepare_trial(
    session: AsyncSession, *, content: str, model_id: str, prompt_id: str | None
) -> tuple[LlmModel, str]:
    """在开始推流前做完全部校验和取数：一旦开始推流就没法再返回 4xx 了。"""

    model = resolve_model(model_id)
    text = _check_message(content)
    if prompt_id and template_variables(text):
        values = await _first_row_values(session, prompt_id)
        text = fill_template(text, values, values.get(CODE_TABLE_FIELD, ""))
    return model, text


async def stream_answer(
    model: LlmModel,
    message: str,
    *,
    thinking: bool,
    previous_response_id: str | None = None,
    echo_prompt: bool = False,
) -> AsyncIterator[str]:
    if echo_prompt:
        yield _sse({"prompt": message})
    yield _sse({"model": model_info(model)})
    body = build_body(model, message, previous_response_id=previous_response_id, thinking=thinking)
    async for event in stream_responses(llm_request(model, body)):
        yield _sse(event)
    yield _sse("[DONE]")


def prepare_chat(model_id: str, message: str) -> tuple[LlmModel, str]:
    return resolve_model(model_id), _check_message(message)
