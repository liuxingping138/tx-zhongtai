from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

FileKind = Literal["excel", "code"]
RunFileKind = Literal["result", "raw", "log", "failed"]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


_MEDIA_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv; charset=utf-8",
}


class TestRowsBody(_Body):
    """从数据库取来的测试数据：存成模板的测试 Excel。"""

    file_name: str = Field(min_length=6, max_length=120, pattern=r"\.xlsx$")
    headers: list[str] = Field(min_length=1, max_length=50)
    rows: list[list[str]] = Field(min_length=1, max_length=200)


class PromptBody(_Body):
    title: str = Field(max_length=255)
    category: str = Field(max_length=16)
    content: str = Field(max_length=200_000)
    output_fields: str = Field(default="", max_length=2000)
    model_id: str = Field(default="", max_length=100)
    code_table: str = Field(default="", max_length=32)
    version: int | None = None


def _price() -> Any:
    return Field(default="", max_length=20)


class ModelBody(_Body):
    """单价按文本收，由应用层统一校验成小数：空串表示没配这一档。"""

    id: str = Field(default="", max_length=64)
    name: str = Field(max_length=100)
    provider: str = Field(max_length=16)
    endpoint: str = Field(max_length=128)
    web_search: bool = False
    thinking: str = Field(default="", max_length=16)
    reasoning_effort: str = Field(default="", max_length=16)
    service_tier: str = Field(default="", max_length=16)
    input_price: str = _price()
    output_price: str = _price()
    flex_input_price: str = _price()
    flex_output_price: str = _price()
    peak_input_price: str = _price()
    peak_output_price: str = _price()
    peak_hours: str = Field(default="", max_length=100)
    search_price: str = _price()
    rate_limit: str = Field(default="", max_length=500)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=100_000)
    version: int | None = None


class AskBody(_Body):
    """row：测试样本第几条数据（从 0 数）；output_fields：编辑页上现在的输出字段，答完按它解析。"""

    content: str = Field(max_length=200_000)
    model_id: str = Field(max_length=100)
    thinking: bool = False
    prompt_id: str | None = Field(default=None, max_length=32)
    row: int = Field(default=0, ge=0, le=100_000)
    output_fields: str = Field(default="", max_length=2000)


class ChatBody(_Body):
    message: str = Field(max_length=200_000)
    model_id: str = Field(max_length=100)
    thinking: bool = False
    previous_response_id: str | None = Field(default=None, max_length=200)


class SampleRunBody(_Body):
    thinking: bool = False
    limit: int = Field(default=10, ge=1, le=50)


def file_response(content: bytes, filename: str) -> Response:
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
    return Response(
        content=content,
        media_type=_MEDIA_TYPES.get(suffix, "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def sse_response(stream: AsyncIterator[str]) -> StreamingResponse:
    # X-Accel-Buffering：前面若有 nginx 也不要缓冲，否则用户要等整段回答生成完才看到字。
    return StreamingResponse(
        stream,
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
