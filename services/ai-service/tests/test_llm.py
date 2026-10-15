from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.llm import LlmRequest, _StreamState, extract_usage, parse_sse_line, stream_responses


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events).encode()


async def _collect(handler: Any) -> list[dict[str, Any]]:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        request = LlmRequest("https://llm.example/v1/", "k", {"model": "m"}, 5.0)
        return [event async for event in stream_responses(request, client)]


async def test_stream_normalizes_text_reasoning_search_usage_and_response_id() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        body = (
            _sse(
                {"type": "response.created", "response": {"id": "tmp"}},
                {"type": "response.reasoning_text.delta", "delta": "想一想"},
                {"type": "response.web_search_call.in_progress"},
                {"type": "response.output_text.delta", "delta": "你好"},
                {"type": "response.output_text.delta", "content": [{"text": "！"}]},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_1",
                        "status": "completed",
                        "usage": {"input_tokens": 10, "output_tokens": 5, "tool_usage": {"web_search": 2}},
                    },
                },
            )
            + b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body)

    events = await _collect(handler)
    assert seen == {"url": "https://llm.example/v1/responses", "auth": "Bearer k"}
    assert events == [
        {"reasoning": "想一想"},
        {"tool_event": {"stage": "web_search_in_progress", "message": "已发起联网搜索"}},
        {"text": "你好"},
        {"text": "！"},
        {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "web_search": 2}},
        {"response_id": "resp_1"},
    ]


async def test_http_error_becomes_readable_message_without_raising() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    assert await _collect(handler) == [{"error": "模型接口返回 HTTP 429：rate limited"}]


async def test_network_failures_are_reported() -> None:
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    def refused(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    assert await _collect(timeout) == [{"error": "模型接口响应超时，请稍后重试"}]
    assert (await _collect(refused))[0]["error"].startswith("无法连接模型接口（ConnectError）")


@pytest.mark.parametrize(
    ("events", "tail"),
    [
        ([{"type": "response.output_text.delta", "delta": "半句"}], "回答被提前截断，未收到完成事件，请稍后重试"),
        ([], "模型未返回任何内容，请稍后重试"),
    ],
)
async def test_stream_without_completion_reports_truncation(events: list[dict[str, Any]], tail: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse(*events))

    assert (await _collect(handler))[-1] == {"error": tail}


def test_failed_events_and_incomplete_status_report_errors_without_response_id() -> None:
    state = _StreamState()
    failed = state.handle({"type": "response.failed", "error": {"message": "坏了"}})
    assert failed == [{"error": "模型未正常完成：坏了"}]
    incomplete = state.handle(
        {
            "type": "response.completed",
            "response": {"id": "r", "status": "incomplete", "incomplete_details": {"reason": "max_tokens"}},
        }
    )
    assert incomplete == [{"error": "模型未正常完成：max_tokens"}]
    assert state.finish() == []
    assert state.handle({"type": "response.output_text.delta", "delta": ""}) == []
    assert state.handle({"type": "response.web_search_call.weird"})[0]["tool_event"]["message"] == "联网搜索：weird"


def test_usage_and_sse_parsing_edge_cases() -> None:
    assert extract_usage({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}) == {
        "input_tokens": 3,
        "output_tokens": 4,
        "total_tokens": 7,
    }
    assert extract_usage({"usage": {}}) is None
    assert extract_usage(None) is None
    assert parse_sse_line("event: x") is None
    assert parse_sse_line("data: not json") is None
    assert parse_sse_line("data: [1]") is None
    assert parse_sse_line('data: {"type": "a"}') == {"type": "a"}
