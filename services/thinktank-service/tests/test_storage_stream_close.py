"""对象存储流式下载：客户端在开始下发前断开时，也要把 httpx 的流式响应关掉，不占着连接池。"""

from __future__ import annotations

import httpx

from app.core import storage
from app.knowledge.api import content_response
from app.knowledge.application import knowledge, knowledge_preview


def _response(body: bytes = b"abc") -> httpx.Response:
    return httpx.Response(200, stream=httpx.ByteStream(body))


async def test_an_unread_stream_is_still_closed() -> None:
    # 从没开始读的异步生成器，aclose 不会执行它的 finally；包装对象直接关响应。
    resp = _response()
    chunks = storage.MinioChunks(resp, 1024, "a.pdf")
    await storage.close_stream(chunks)
    assert resp.is_closed


async def test_a_fully_read_stream_closes_once_and_closing_again_is_harmless() -> None:
    resp = _response(b"hello")
    chunks = storage.MinioChunks(resp, 2, "a.pdf")
    assert b"".join([chunk async for chunk in chunks]) == b"hello"
    assert resp.is_closed
    await storage.close_stream(chunks)


async def test_local_streams_without_aclose_are_ignored() -> None:
    class Plain:
        def __aiter__(self) -> Plain:
            return self

        async def __anext__(self) -> bytes:
            raise StopAsyncIteration

    await storage.close_stream(Plain())


def test_file_responses_close_the_stream_in_the_background() -> None:
    resp = _response()
    result = knowledge_preview.FileStreamResult(
        stream=storage.MinioChunks(resp, 1024, "a.pdf"), filename="a.pdf", media_type="application/pdf"
    )
    response = content_response.streamed(result, {})
    assert response.background is not None
    assert response.background.func is knowledge.close_file_stream
    assert response.background.args == (result,)
