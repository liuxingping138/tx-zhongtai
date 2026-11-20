"""问一行：调一次模型拿到回答、用量和错误，按规则当场补救；以及哪些失败值得下一轮再问。批量任务的执行（batch_execute）用它。"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
from typing import Any

import httpx

from app.application.asking import llm_request
from app.application.batch_output import FORMAT_ERROR_PREFIX, RowResult, answered
from app.application.billing import TOKENS_PER_CHAR
from app.core.llm import stream_responses
from app.domain.llm_models import LlmModel, build_body

# 可重试错误的退避秒数，次数即重试次数；实际等待再乘 1~1.5 的随机系数，避免 20 路并发同时撞回去。
RETRY_DELAYS = (3.0, 10.0)
# 样本试跑格式不对当场再问的次数。分轮的任务不当场再问，交给下一轮：一行坏数据每问一次都带着码表全文、按全价收钱。
FORMAT_RETRIES = 1


async def call_model_once(model: LlmModel, prompt: str, thinking: bool, client: httpx.AsyncClient) -> RowResult:
    """消费整条流，只要最终文本、用量、错误和联网次数。联网次数优先用 usage 里的权威值，没有就数进度事件。"""

    started = time.monotonic()
    parts: list[str] = []
    usage: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    search_events = 0
    reasoning_chars = 0
    async for event in stream_responses(llm_request(model, build_body(model, prompt, thinking=thinking)), client):
        if "text" in event:
            parts.append(event["text"])
        elif "reasoning" in event:
            reasoning_chars += len(str(event["reasoning"] or ""))
        elif "usage" in event:
            usage = event["usage"]
        elif "error" in event:
            errors.append(event)
        elif event.get("tool_event", {}).get("stage") == "web_search_in_progress":
            search_events += 1
    text = "".join(parts)
    if errors and not usage and (text or reasoning_chars):
        # 写出一部分后断了（截断、读超时）：厂商照收读进去的提示词和写出来的部分，没等到用量就按字数估，
        # 和试发、对话中途断开同一口径（billing.CallTally.estimate）。原来记 0 再重发，账单和打标的费用上限都少算。
        usage = {
            "input_tokens": math.ceil(len(prompt) * TOKENS_PER_CHAR),
            "output_tokens": math.ceil((len(text) + reasoning_chars) * TOKENS_PER_CHAR),
        }
    return RowResult(
        myid="",
        prompt=prompt,
        text=text,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cached_tokens=usage.get("cached_tokens", 0),
        search_calls=usage.get("web_search", search_events),
        error=errors[-1]["error"] if errors else "",
        elapsed=round(time.monotonic() - started, 2),
        retryable=bool(errors and errors[-1].get("retryable")),
    )


def needs_retry(result: RowResult, fields: list[str]) -> bool:
    return not answered(result, fields)


def round_retry(result: RowResult) -> bool:
    """这一轮失败、下一轮值得再问的：网络类（超时、断连、限流、5xx、空返回）和格式不对。
    400、密钥错误、回答写到上限被截停这类，隔几分钟再问结果也一样，白花钱，不重问。"""

    return bool(result.error) and (result.retryable or result.format_error)


async def ask_row(  # noqa: PLR0913  请求参数与停止信号各自独立，保持直白签名便于测试调用
    model: LlmModel,
    prompt: str,
    thinking: bool,
    fields: list[str],
    client: httpx.AsyncClient,
    *,
    format_retries: int = FORMAT_RETRIES,
    stop: asyncio.Event | None = None,
) -> RowResult:
    """问一行，按规则自动补救。几次尝试的 token 和联网次数都算进这一行：钱已经花出去了。"""

    delays = list(RETRY_DELAYS)
    spent = [0, 0, 0, 0]
    attempts = 0
    while True:
        result = await call_model_once(model, prompt, thinking, client)
        attempts += 1
        spent = [
            spent[0] + result.input_tokens,
            spent[1] + result.output_tokens,
            spent[2] + result.search_calls,
            spent[3] + result.cached_tokens,
        ]
        if result.error and result.retryable and delays:
            delay = delays.pop(0) * random.uniform(1.0, 1.5)  # noqa: S311  退避抖动，不涉及安全
            if stop is None:
                await asyncio.sleep(delay)
            else:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                if stop.is_set():
                    break
            continue
        if not result.error and needs_retry(result, fields):
            if format_retries:
                format_retries -= 1
                continue
            result.error = f"{FORMAT_ERROR_PREFIX}：回答里没有解析出输出字段（{'、'.join(fields)}）"
        break
    result.input_tokens, result.output_tokens, result.search_calls, result.cached_tokens = spent
    result.attempts = attempts
    return result
