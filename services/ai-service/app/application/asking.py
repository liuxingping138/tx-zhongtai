"""流式提问：提问配置页的试发、多轮对话。

返回 SSE 文本块：每块 `data: {json}\\n\\n`，最后一块 `data: [DONE]`。事件见 app.core.llm，另加：
    {"prompt": 实际发出的提示词}   试发时第一块，变量已替换成测试样本所选那一行的值
    {"model": {...}}               本次使用的模型，前端据此算费用
    {"parsed": [{字段: 值}] | null} 试发带了输出字段时最后一块：按输出字段解析的结果，null 表示格式不对
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, PermissionDeniedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import model_configs, test_rows
from app.application.billing import CallTally
from app.application.prompts import code_text, require, require_editable
from app.core.config import get_settings
from app.core.llm import LlmRequest, stream_responses
from app.domain.categories import CategoryAccess
from app.domain.llm_models import LlmModel, build_body
from app.domain.templating import CODE_TABLE_FIELD, fill_template, parse_fields, template_variables

MESSAGE_MAX = 200_000


def _sse(payload: dict[str, Any] | str) -> str:
    data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f"data: {data}\n\n"


def api_key_for(model: LlmModel) -> str:
    settings = get_settings()
    return settings.ark_api_key if model.provider == "ark" else settings.baidu_api_key


def model_info(model: LlmModel) -> dict[str, Any]:
    """单价按此刻算：分时计价的模型，前端据此估算这次对话的费用。"""

    now = utcnow()
    input_price, output_price = model.prices_at(now)
    return {
        "id": model.id,
        "name": model.name,
        "provider": model.provider_name,
        "web_search": model.web_search,
        "supports_thinking": model.supports_thinking,
        "available": bool(api_key_for(model)),
        "input_price": str(input_price),
        "output_price": str(output_price),
        "search_price": str(model.search_price),
        "price_note": model.price_note(now),
    }


async def available_models(session: AsyncSession) -> list[dict[str, Any]]:
    """页面下拉里的模型：只列启用的。"""

    return [model_info(model) for model in await model_configs.enabled_models(session)]


RELEASE_MODEL_DISABLED = "它是上线版本用的模型，请改模板的模型后重新上线"


async def resolve_model(session: AsyncSession, model_id: str, *, frozen: str = "") -> LlmModel:
    """frozen：模型不是页面上现选的（上线版本、任务快照里冻结的）时，停用提示里说清该去哪改。"""

    row = await model_configs.find(session, model_id)
    if row is None:
        raise ApiError(f"未知模型：{model_id or '（未选择）'}", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not row.enabled:
        raise ApiError(
            f"模型「{row.name}」已停用，{frozen or '请换一个模型'}", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    model = model_configs.to_model(row)
    if not api_key_for(model):
        raise ApiError(
            f"{model.provider_name}的接口密钥未配置，暂不能使用该模型",
            http_status=503,
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        )
    return model


def llm_request(model: LlmModel, body: dict[str, Any]) -> LlmRequest:
    settings = get_settings()
    return LlmRequest(
        settings.llm_base_url or model.base_url, api_key_for(model), body, settings.llm_read_timeout_seconds
    )


def _check_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        raise ApiError("提问内容不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if len(text) > MESSAGE_MAX:
        raise ApiError("提问内容过长", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return text


async def _row_values(session: AsyncSession, prompt_id: str, row: int) -> dict[str, str]:
    """测试样本第 row 条数据（从 0 数）+ 码表全文（上传的或系统码表），用来把 @【列名】@【上传码表】替换成真实值。"""

    template = await require(session, prompt_id)
    values = dict(await test_rows.row_values(template, row))
    code = await code_text(template)
    if code is not None:
        values[CODE_TABLE_FIELD] = code
    return values


async def prepare_trial(
    session: AsyncSession,
    access: CategoryAccess,
    *,
    content: str,
    model_id: str,
    prompt_id: str | None,
    row: int = 0,
) -> tuple[LlmModel, str]:
    """在开始推流前做完全部校验和取数：一旦开始推流就没法再返回 4xx 了。

    试发要花钱：存过的模板按它的类型要编辑权；还没保存的新模板，至少能在某个类型下编辑。
    """

    if prompt_id:
        await require_editable(session, access, prompt_id)
    elif not access.editable:
        raise PermissionDeniedError("没有编辑任何类型模板的权限，不能试发")
    model = await resolve_model(session, model_id)
    text = _check_message(content)
    if prompt_id and template_variables(text):
        values = await _row_values(session, prompt_id, row)
        text = fill_template(text, values, values.get(CODE_TABLE_FIELD, ""))
    return model, text


async def stream_answer(
    model: LlmModel,
    message: str,
    *,
    thinking: bool,
    previous_response_id: str | None = None,
    trial_fields: list[str] | None = None,
    on_done: Callable[[CallTally], Awaitable[None]] | None = None,
) -> AsyncIterator[str]:
    """推流回答。答完把这次的用量交给 on_done 记账；用户中途停止时模型还没给用量，这次不记。

    trial_fields 只在试发时给（模板的输出字段，可以为空）：先回显实际发出的提示词，答完按和批量任务同一套规则解析，
    页面直接看出这一行能不能解析、解析成什么。
    """

    fields = trial_fields or []
    if trial_fields is not None:
        yield _sse({"prompt": message})
    yield _sse({"model": model_info(model)})
    body = build_body(model, message, previous_response_id=previous_response_id, thinking=thinking)
    tally = CallTally()
    parts: list[str] = []
    failed = False
    async for event in stream_responses(llm_request(model, body)):
        tally.add(event)
        parts.append(str(event.get("text") or ""))
        failed = failed or bool(event.get("error"))
        yield _sse(event)
    if fields and not failed:
        yield _sse({"parsed": parse_fields("".join(parts), fields)})
    if on_done is not None:
        await on_done(tally)
    yield _sse("[DONE]")


async def prepare_chat(session: AsyncSession, model_id: str, message: str) -> tuple[LlmModel, str]:
    return await resolve_model(session, model_id), _check_message(message)
