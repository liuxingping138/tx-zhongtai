"""P6 隔离验收用的模拟模型服务：按 Responses 流式接口回答，不花钱也能跑通试发、样本试跑和批量任务。

只在 P6 栈里起（docker-compose.p6.yml 的 llm-mock），ai-service 经 AI_LLM_BASE_URL 指过来；生产环境配不了这个地址。
回答规则：
- 提示词里有「返回字段：甲、乙」（「把格式要求追加到提示词」生成的）就回 [{"甲": ..., "乙": ...}]，否则回一句话；
- 含「模拟格式错误」：永远回一句没有 JSON 的话，验证「格式不对」；
- 含「模拟调用失败」：同一段提示词第一次回 HTTP 400、之后正常，验证失败行和「重跑失败」。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

_FIELDS = re.compile(r"返回字段：([^\n]+)")
_failed_once: set[str] = set()


def _message(body: dict[str, object]) -> str:
    items = body.get("input")
    if isinstance(items, list) and items and isinstance(items[-1], dict):
        return str(items[-1].get("content") or "")
    return ""


def _answer(message: str, digest: str) -> str:
    if "模拟格式错误" in message:
        return "这一条我没法按格式回答。"
    match = _FIELDS.search(message)
    if not match:
        return f"模拟回答（{digest[:6]}）：已读完提示词，共 {len(message)} 字。"
    fields = [name.strip() for name in re.split(r"[、,，|]", match.group(1)) if name.strip()]
    return json.dumps([{name: f"{name}-{digest[:4]}" for name in fields}], ensure_ascii=False)


def _event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream(text: str, message: str, digest: str) -> AsyncIterator[str]:
    step = max(len(text) // 3, 1)
    for start in range(0, len(text), step):
        await asyncio.sleep(0.05)
        yield _event({"type": "response.output_text.delta", "delta": text[start : start + step]})
    usage = {"input_tokens": len(message), "output_tokens": len(text), "total_tokens": len(message) + len(text)}
    response = {"id": f"resp_{digest[:16]}", "status": "completed", "usage": usage}
    yield _event({"type": "response.completed", "response": response})


async def responses(request: Request) -> Response:
    body = await request.json()
    message = _message(body if isinstance(body, dict) else {})
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    if "模拟调用失败" in message and digest not in _failed_once:
        _failed_once.add(digest)
        return JSONResponse({"error": {"message": "模拟的参数错误"}}, status_code=400)
    return StreamingResponse(_stream(_answer(message, digest), message, digest), media_type="text/event-stream")


async def health(_: Request) -> Response:
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/responses", responses, methods=["POST"]), Route("/health", health)])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099, log_level="warning")  # noqa: S104  只在 P6 内部网络里监听
