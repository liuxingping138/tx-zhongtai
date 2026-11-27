"""智库通用 `/content`、`/download` 流式与 HTTP Range（206 / 416 / 304）响应拼装。"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi.responses import Response, StreamingResponse
from platform_common.http_utils import content_disposition as build_content_disposition
from starlette.background import BackgroundTask

from app.common.preview import FileStreamResult, close_file_stream
from app.core import preview_cache

_RANGE_SPEC = re.compile(r"^(\d*)-(\d*)$")
_HTTP_PARTIAL = 206
_HTTP_NOT_MODIFIED = 304
_HTTP_RANGE_NOT_SATISFIABLE = 416

CloseFn = Callable[[FileStreamResult], Awaitable[None]]


class RangeNotSatisfiableError(ValueError):
    """Range 写法不对或起点超出文件。"""


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def content_disposition(disposition: str, filename: str, *, fallback: str = "thinktank-file") -> str:
    return build_content_disposition(disposition, filename, fallback=fallback)


def _bounds(first: str, last: str, total: int) -> ByteRange:
    if not first:
        suffix = int(last)
        if suffix == 0:
            raise RangeNotSatisfiableError
        return ByteRange(max(total - suffix, 0), total - 1)
    start = int(first)
    end = int(last) if last else total - 1
    if start > end or start >= total:
        raise RangeNotSatisfiableError
    return ByteRange(start, min(end, total - 1))


def parse_range(header: str | None, total: int) -> ByteRange | None:
    if not header:
        return None
    unit, _, spec = header.strip().partition("=")
    if unit.strip().lower() != "bytes":
        return None
    if "," in spec:
        return None
    matched = _RANGE_SPEC.match(spec.strip())
    if matched is None or not (matched.group(1) or matched.group(2)) or total <= 0:
        raise RangeNotSatisfiableError
    return _bounds(matched.group(1), matched.group(2), total)


def streamed(
    res: FileStreamResult,
    headers: dict[str, str],
    *,
    status_code: int = 200,
    closer: CloseFn = close_file_stream,
) -> StreamingResponse:
    background = BackgroundTask(closer, res)
    return StreamingResponse(
        res.stream, status_code=status_code, media_type=res.media_type, headers=headers, background=background
    )


def _closed(
    res: FileStreamResult,
    headers: dict[str, str],
    *,
    status_code: int,
    closer: CloseFn = close_file_stream,
) -> Response:
    background = BackgroundTask(closer, res)
    return Response(status_code=status_code, media_type=res.media_type, headers=headers, background=background)


def not_modified(etag: str) -> Response:
    return Response(
        status_code=_HTTP_NOT_MODIFIED,
        headers={"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Authorization"},
    )


def _base_headers(res: FileStreamResult, *, fallback: str) -> dict[str, str]:
    headers = {
        "Content-Disposition": content_disposition("inline", res.filename, fallback=fallback),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache" if res.etag else "private, no-store",
    }
    if res.etag:
        headers["ETag"] = res.etag
        headers["Vary"] = "Authorization"
    return headers


def _ranged_response(
    res: FileStreamResult,
    *,
    head: bool,
    range_header: str | None,
    if_range: str | None,
    fallback: str,
    closer: CloseFn,
) -> Response:
    total = res.content_length or 0
    headers = {**_base_headers(res, fallback=fallback), "Accept-Ranges": "bytes"}
    if if_range is not None and if_range.strip() != res.etag:
        range_header = None
    try:
        selected = parse_range(range_header, total)
    except RangeNotSatisfiableError:
        headers["Content-Range"] = f"bytes */{total}"
        return _closed(res, headers, status_code=_HTTP_RANGE_NOT_SATISFIABLE, closer=closer)
    if selected is None:
        headers["Content-Length"] = str(total)
        return _closed(res, headers, status_code=200, closer=closer) if head else streamed(res, headers, closer=closer)
    headers["Content-Range"] = f"bytes {selected.start}-{selected.end}/{total}"
    headers["Content-Length"] = str(selected.length)
    if head:
        return _closed(res, headers, status_code=_HTTP_PARTIAL, closer=closer)
    if isinstance(res.stream, preview_cache.FileChunks):
        res.stream.select_range(selected.start, selected.length)
    return streamed(res, headers, status_code=_HTTP_PARTIAL, closer=closer)


def inline_content_response(
    res: FileStreamResult,
    *,
    head: bool,
    range_header: str | None,
    if_range: str | None,
    fallback: str = "thinktank-file",
    closer: CloseFn = close_file_stream,
) -> Response:
    if res.not_modified and res.etag:
        return not_modified(res.etag)
    if res.ranged and res.content_length is not None:
        return _ranged_response(
            res, head=head, range_header=range_header, if_range=if_range, fallback=fallback, closer=closer
        )
    headers = _base_headers(res, fallback=fallback)
    if res.content_length is not None:
        headers["Content-Length"] = str(res.content_length)
    return _closed(res, headers, status_code=200, closer=closer) if head else streamed(res, headers, closer=closer)
