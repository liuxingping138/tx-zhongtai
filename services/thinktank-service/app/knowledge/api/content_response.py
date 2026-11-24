"""`/content`、`/download` 的响应拼装：Content-Disposition、流式下发，以及预览 PDF 的 HTTP Range（206 / 416）。

预览用 PDF 是本地缓存文件（压缩、线性化过），前端 PDF.js 按 Range 一段段取，第一页只要头几百 KB。
只认单段 Range（`bytes=a-b`、`bytes=a-`、`bytes=-n`）；多段直接回整份 200（RFC 9110 允许忽略），
写法不对或起点超出文件回 416。`If-Range` 对不上 ETag 时忽略 Range、回整份，免得拼出新旧两份文件混在一起的内容。
文本摘要、对象存储直读的原文件不是本地文件，不支持 Range，照旧整份下发。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from app.core import preview_cache
from app.knowledge.application import knowledge as service
from app.knowledge.application.knowledge_preview import FileStreamResult

_UNSAFE_HEADER_CHARS = re.compile(r'[\x00-\x1f\x7f"\\]')
_RANGE_SPEC = re.compile(r"^(\d*)-(\d*)$")
_HTTP_PARTIAL = 206
_HTTP_NOT_MODIFIED = 304
_HTTP_RANGE_NOT_SATISFIABLE = 416


class RangeNotSatisfiableError(ValueError):
    """Range 写法不对或起点超出文件。"""


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int  # 含

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def content_disposition(disposition: str, filename: str) -> str:
    safe_name = _UNSAFE_HEADER_CHARS.sub("_", filename).strip() or "knowledge-file"
    ascii_fallback = safe_name.encode("ascii", "ignore").decode("ascii").strip() or "knowledge-file"
    encoded = quote(safe_name)
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _bounds(first: str, last: str, total: int) -> ByteRange:
    if not first:  # bytes=-n：最后 n 个字节
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
    """解析单段 Range。没有 Range、不是 bytes 单位、多段时返回 None（回整份）；

    写法不对、不能满足时抛 RangeNotSatisfiableError。
    """

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


def streamed(res: FileStreamResult, headers: dict[str, str], *, status_code: int = 200) -> StreamingResponse:
    # 客户端在开始下发前断开时流从没被读过，不主动关的话对象存储的连接要等垃圾回收才释放。
    background = BackgroundTask(service.close_file_stream, res)
    return StreamingResponse(
        res.stream, status_code=status_code, media_type=res.media_type, headers=headers, background=background
    )


def _closed(res: FileStreamResult, headers: dict[str, str], *, status_code: int) -> Response:
    """不带正文的响应（HEAD、416）：已经打开的缓存文件在响应发完后关掉。"""

    background = BackgroundTask(service.close_file_stream, res)
    return Response(status_code=status_code, media_type=res.media_type, headers=headers, background=background)


def not_modified(etag: str) -> Response:
    return Response(
        status_code=_HTTP_NOT_MODIFIED,
        headers={"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Authorization"},
    )


def _base_headers(res: FileStreamResult) -> dict[str, str]:
    headers = {
        "Content-Disposition": content_disposition("inline", res.filename),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache" if res.etag else "private, no-store",
    }
    if res.etag:
        headers["ETag"] = res.etag
        headers["Vary"] = "Authorization"
    return headers


def _ranged_response(res: FileStreamResult, *, head: bool, range_header: str | None, if_range: str | None) -> Response:
    total = res.content_length or 0
    headers = {**_base_headers(res), "Accept-Ranges": "bytes"}
    if if_range is not None and if_range.strip() != res.etag:
        range_header = None
    try:
        selected = parse_range(range_header, total)
    except RangeNotSatisfiableError:
        headers["Content-Range"] = f"bytes */{total}"
        return _closed(res, headers, status_code=_HTTP_RANGE_NOT_SATISFIABLE)
    if selected is None:
        headers["Content-Length"] = str(total)
        return _closed(res, headers, status_code=200) if head else streamed(res, headers)
    headers["Content-Range"] = f"bytes {selected.start}-{selected.end}/{total}"
    headers["Content-Length"] = str(selected.length)
    if head:
        return _closed(res, headers, status_code=_HTTP_PARTIAL)
    if isinstance(res.stream, preview_cache.FileChunks):
        res.stream.select_range(selected.start, selected.length)
    return streamed(res, headers, status_code=_HTTP_PARTIAL)


def inline_content_response(
    res: FileStreamResult, *, head: bool, range_header: str | None, if_range: str | None
) -> Response:
    """预览原文的响应：本地缓存的 PDF 支持 Range 和 HEAD，其余整份下发。"""

    if res.not_modified and res.etag:
        return not_modified(res.etag)
    if res.ranged and res.content_length is not None:
        return _ranged_response(res, head=head, range_header=range_header, if_range=if_range)
    headers = _base_headers(res)
    if res.content_length is not None:
        headers["Content-Length"] = str(res.content_length)
    return _closed(res, headers, status_code=200) if head else streamed(res, headers)
