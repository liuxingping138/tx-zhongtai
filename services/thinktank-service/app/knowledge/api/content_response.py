"""资料库 `/content`、`/download` 响应拼装，复用 app.common.content_response。"""

from __future__ import annotations

from fastapi.responses import Response, StreamingResponse

from app.common import content_response as common_cr
from app.common.content_response import ByteRange, RangeNotSatisfiableError, not_modified, parse_range
from app.knowledge.application import knowledge as service
from app.knowledge.application.knowledge_preview import FileStreamResult

__all__ = [
    "ByteRange",
    "RangeNotSatisfiableError",
    "content_disposition",
    "inline_content_response",
    "not_modified",
    "parse_range",
    "streamed",
]


def content_disposition(disposition: str, filename: str) -> str:
    return common_cr.content_disposition(disposition, filename, fallback="knowledge-file")


def streamed(res: FileStreamResult, headers: dict[str, str], *, status_code: int = 200) -> StreamingResponse:
    return common_cr.streamed(res, headers, status_code=status_code, closer=service.close_file_stream)


def inline_content_response(
    res: FileStreamResult, *, head: bool, range_header: str | None, if_range: str | None
) -> Response:
    return common_cr.inline_content_response(
        res,
        head=head,
        range_header=range_header,
        if_range=if_range,
        fallback="knowledge-file",
        closer=service.close_file_stream,
    )
