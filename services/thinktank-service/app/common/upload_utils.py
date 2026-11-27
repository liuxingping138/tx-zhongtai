"""智库通用上传、文件名清洗、尺寸格式化与多值筛选工具。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from pathlib import PureWindowsPath
from typing import Any

from fastapi import Request
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import LIKE_ESCAPE, escape_like
from platform_common.http_utils import MULTIPART_OVERHEAD_BYTES, read_upload_within_limit
from sqlalchemy import ColumnElement, or_
from starlette.formparsers import MultiPartException, MultiPartParser

_DEFINED_TOKENS = frozenset({"已定义", "defined", "true", "1"})
_UNDEFINED_TOKENS = frozenset({"未定义", "undefined", "false", "0"})
_FAVORITE_TOKENS = frozenset({"已收藏", "仅已收藏", "仅看收藏", "true", "1", "yes"})


def format_size(size_bytes: int) -> str:
    return f"{size_bytes / 1024:.2f} kb"


def sanitize_filename(raw: str) -> str:
    """剥离上传或改名时夹带的目录路径（含 Windows 盘符与反斜杠），只留纯文件名。"""

    stripped = raw.strip()
    if not stripped or stripped.endswith(("/", "\\")):
        return ""
    name = PureWindowsPath(stripped.replace("/", "\\")).name.strip()
    return "" if name in {"", ".", ".."} else name


def sanitize_title(raw: str) -> str:
    """清洗报告/方案展示标题：去首尾空白，拒绝纯点号。"""

    stripped = raw.strip()
    return "" if stripped in {"", ".", ".."} else stripped


def merge_unique(*groups: Sequence[str]) -> list[str]:
    """按顺序合并去重并过滤空串。"""

    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def split_pipe_values(raw: str | None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def normalize_pipe_value(raw: str | None) -> str:
    return "|".join(dict.fromkeys(split_pipe_values(raw)))


def expand_pipe_options(values: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in split_pipe_values(raw):
            if part not in seen:
                seen.add(part)
                expanded.append(part)
    return expanded


def pipe_match(column: Any, value: str) -> ColumnElement[bool]:
    escaped = escape_like(value)
    return or_(
        column == value,
        column.like(f"{escaped}|%", escape=LIKE_ESCAPE),
        column.like(f"%|{escaped}", escape=LIKE_ESCAPE),
        column.like(f"%|{escaped}|%", escape=LIKE_ESCAPE),
    )


def parse_tag_status_filter(vals: Sequence[str]) -> bool | None:
    lowered = {v.strip().lower() for v in vals}
    want_def = bool(lowered & _DEFINED_TOKENS)
    want_undef = bool(lowered & _UNDEFINED_TOKENS)
    if want_def != want_undef:
        return want_def
    return None


def parse_favorite_only_filter(vals: Sequence[str]) -> bool:
    return any(v.strip().lower() in _FAVORITE_TOKENS for v in vals)


def _merge_request_fields(request: Request, form: Any) -> dict[str, str]:
    fields = {k: v for k, v in request.query_params.items() if v != ""}
    form_fields = {
        key: value for key, value in form.multi_items() if key != "file" and isinstance(value, str) and value != ""
    }
    return {**fields, **form_fields}


async def read_upload_with_fields(
    request: Request,
    max_bytes: int,
    *,
    missing: str = "请上传文件",
    max_fields: int = 32,
) -> tuple[bytes, str, dict[str, str]]:
    """在鉴权通过后流式解析 multipart：同时返回文件内容、原始文件名与非文件文本字段（合并 query 参数）。"""

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise ApiError(missing, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    received = 0
    limit = max_bytes + MULTIPART_OVERHEAD_BYTES

    async def chunks() -> AsyncGenerator[bytes, None]:
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                raise ApiError("上传文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=413)
            yield chunk

    parser = MultiPartParser(
        request.headers,
        chunks(),
        max_files=2,
        max_fields=max_fields,
        max_part_size=max_bytes,
    )
    try:
        form = await parser.parse()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise ApiError(missing, code=ErrorCode.VALIDATION_ERROR, http_status=422)
        if upload.size is not None and upload.size > max_bytes:
            raise ApiError("上传文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=413)
        content = await read_upload_within_limit(upload, max_bytes)
        return content, upload.filename or "", _merge_request_fields(request, form)
    except MultiPartException as exc:
        raise ApiError("上传表单无效或超过限制", code=ErrorCode.VALIDATION_ERROR, http_status=413) from exc
    finally:
        for temporary in parser._files_to_close_on_error:
            temporary.close()
