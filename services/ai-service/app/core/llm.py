"""大模型 Responses 接口的流式客户端。字节方舟和百度千帆的 /responses 事件格式一致，共用这一份。

只做两件事：发请求、把服务端事件归一成下面几种字典，逐个产出：
    {"text": 增量}          {"reasoning": 思考过程增量}
    {"tool_event": {...}}   联网搜索进度
    {"usage": {...}}        token 用量（含命中上下文缓存的 cached_tokens），联网次数在 usage["web_search"]
    {"error": 中文说明}     {"response_id": id}  只在正常完成时给，供多轮对话接续
错误事件可能带 "retryable": True：限流、5xx、超时、断连、被截断，换个时间重发大概率能成功。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

_CONNECT_TIMEOUT = 10.0
_ERROR_BODY_LIMIT = 300
_RATE_LIMITED = 429
_SERVER_ERROR = 500
_COMPLETED = ("response.completed", "response.done")
_FAILED = ("response.failed", "response.incomplete", "response.error", "error")
_OK_STATUSES = ("completed", "succeeded", "success")
_SEARCH_TIPS = {
    "in_progress": "已发起联网搜索",
    "searching": "正在检索网络信息",
    "completed": "联网搜索完成，整理结果中",
}


@dataclass(frozen=True)
class LlmRequest:
    base_url: str
    api_key: str
    body: dict[str, Any]
    read_timeout: float


def _pick(source: Any, *keys: str) -> Any:
    for key in keys:
        value = source.get(key) if isinstance(source, dict) else None
        if value is not None:
            return value
    return None


def _cached_tokens(usage: dict[str, Any], input_tokens: int) -> int:
    """输入里命中上下文缓存的 token。各家写法不同，按 Responses、Chat Completions、平铺的顺序找，都没有算 0。
    夹在 0 到输入 token 之间：缓存部分按缓存价、其余按输入价算钱，超出输入数会算出负的未命中部分。"""

    for parent in ("input_tokens_details", "prompt_tokens_details"):
        value = _pick(_pick(usage, parent), "cached_tokens")
        if value is not None:
            break
    else:
        value = _pick(usage, "cached_tokens")
    try:
        cached = int(value or 0)
    except (TypeError, ValueError):
        cached = 0
    return min(max(cached, 0), input_tokens)


def extract_usage(response: Any) -> dict[str, int] | None:
    """统一成 input/output/total/cached_tokens；方舟在 usage.tool_usage.web_search 给权威的联网次数。"""

    usage = _pick(response, "usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = _pick(usage, "input_tokens", "prompt_tokens")
    output_tokens = _pick(usage, "output_tokens", "completion_tokens")
    if input_tokens is None and output_tokens is None:
        return None
    result = {"input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0)}
    result["cached_tokens"] = _cached_tokens(usage, result["input_tokens"])
    result["total_tokens"] = int(_pick(usage, "total_tokens") or result["input_tokens"] + result["output_tokens"])
    searches = _pick(_pick(usage, "tool_usage"), "web_search")
    if isinstance(searches, int | str) and str(searches).isdigit():
        result["web_search"] = int(searches)
    return result


def error_message(event: Any) -> str:
    for path in (
        ("error", "message"),
        ("error", "msg"),
        ("response", "error", "message"),
        ("response", "incomplete_details", "reason"),
        ("message",),
    ):
        current = event
        for key in path:
            current = current.get(key) if isinstance(current, dict) else None
        if current:
            return str(current)[:_ERROR_BODY_LIMIT]
    return "服务端未提供详细错误信息"


def _delta_text(event: dict[str, Any]) -> str:
    text = event.get("delta") or event.get("reasoning") or ""
    content = event.get("content")
    if not text and isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text") or ""
    return text if isinstance(text, str) else ""


class _StreamState:
    def __init__(self) -> None:
        self.completed = False
        self.emitted_text = False

    def handle(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = str(event.get("type") or "")
        if kind == "response.output_text.delta":
            text = _delta_text(event)
            self.emitted_text = self.emitted_text or bool(text)
            return [{"text": text}] if text else []
        if kind.startswith(("response.reasoning", "response.thinking")) and kind.endswith(".delta"):
            text = _delta_text(event)
            return [{"reasoning": text}] if text else []
        if kind.startswith("response.web_search_call."):
            stage = kind.rsplit(".", 1)[-1]
            message = _SEARCH_TIPS.get(stage, f"联网搜索：{stage}")
            return [{"tool_event": {"stage": f"web_search_{stage}", "message": message}}]
        if kind in _FAILED:
            self.completed = True
            # 写到输出上限被截停、内容被过滤时厂商照样按 token 收钱，用量要记上，不然账单少算。
            usage = extract_usage(event.get("response"))
            return [{"error": f"模型未正常完成：{error_message(event)}"}, *([{"usage": usage}] if usage else [])]
        if kind in _COMPLETED:
            self.completed = True
            return self._completed(event)
        return []

    @staticmethod
    def _completed(event: dict[str, Any]) -> list[dict[str, Any]]:
        raw = event.get("response")
        response: dict[str, Any] = raw if isinstance(raw, dict) else {}
        out: list[dict[str, Any]] = []
        status = response.get("status")
        failed = bool(status) and status not in _OK_STATUSES
        if failed:
            out.append({"error": f"模型未正常完成：{error_message(event)}"})
        usage = extract_usage(response)
        if usage:
            out.append({"usage": usage})
        # 只采纳完成事件里的 id：response.created 里的是临时的，没走到完成服务端不保存，下一轮带上去会报找不到。
        if response.get("id") and not failed:
            out.append({"response_id": response["id"]})
        return out

    def finish(self) -> list[dict[str, Any]]:
        if self.completed:
            return []
        if self.emitted_text:
            return [{"error": "回答被提前截断，未收到完成事件，请稍后重试", "retryable": True}]
        return [{"error": "模型未返回任何内容，请稍后重试", "retryable": True}]


def parse_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


async def _http_error(response: httpx.Response) -> str:
    body = (await response.aread()).decode("utf-8", "replace")
    try:
        detail = error_message(json.loads(body))
    except json.JSONDecodeError:
        detail = body[:_ERROR_BODY_LIMIT] or "无响应内容"
    return f"模型接口返回 HTTP {response.status_code}：{detail}"


async def stream_responses(
    request: LlmRequest, client: httpx.AsyncClient | None = None
) -> AsyncIterator[dict[str, Any]]:
    """发起一次流式调用。网络异常、非 2xx 都转成 {"error": ...} 产出，不抛给调用方，批量里一条失败不拖垮整批。"""

    timeout = httpx.Timeout(request.read_timeout, connect=_CONNECT_TIMEOUT)
    owned = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    state = _StreamState()
    headers = {
        "Authorization": f"Bearer {request.api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = request.base_url.rstrip("/") + "/responses"
    try:
        async with http.stream("POST", url, json=request.body, headers=headers, timeout=timeout) as response:
            if response.status_code // 100 != 2:  # noqa: PLR2004  2xx 判断
                retryable = response.status_code == _RATE_LIMITED or response.status_code >= _SERVER_ERROR
                yield {"error": await _http_error(response), "retryable": retryable}
                return
            async for line in response.aiter_lines():
                event = parse_sse_line(line)
                if event is None:
                    continue
                for item in state.handle(event):
                    yield item
        for item in state.finish():
            yield item
    except httpx.TimeoutException:
        yield {"error": "模型接口响应超时，请稍后重试", "retryable": True}
    except httpx.HTTPError as exc:
        yield {"error": f"无法连接模型接口（{type(exc).__name__}），请稍后重试", "retryable": True}
    finally:
        if owned:
            await http.aclose()
