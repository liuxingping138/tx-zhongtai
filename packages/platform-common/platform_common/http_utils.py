from __future__ import annotations

import base64
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from platform_common.errors import ApiError, ErrorCode
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse

_UPLOAD_CHUNK_BYTES = 1024 * 1024
# multipart 边界和字段头。网关与应用的总字节上限都要留出这段，20MB 的 Excel 才能通过。
MULTIPART_OVERHEAD_BYTES = 256 * 1024

IMPORT_FILE_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


def success_json(data: Any = None, *, status_code: int = 200, message: str = "success") -> JSONResponse:
    body = ApiResponse(code="OK", message=message, data=data, request_id=get_request_id())
    return JSONResponse(status_code=status_code, content=body.model_dump())


def import_result_response(result: dict[str, Any], filename: str) -> Response:
    raw = result.get("skipped_file")
    if not raw:
        clean = {key: value for key, value in result.items() if key != "skipped_file"}
        return success_json(clean)
    payload = base64.b64decode(raw) if isinstance(raw, str) else raw
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Import-Rejected": "1" if result.get("rejected") else "0",
            "X-Import-Inserted": str(result.get("inserted", 0)),
            "X-Import-Updated": str(result.get("updated", 0)),
            "X-Import-Skipped": str(result.get("skipped", 0)),
            "X-Import-Total": str(result.get("total", 0)),
            "Access-Control-Expose-Headers": (
                "X-Import-Rejected, X-Import-Inserted, X-Import-Updated, "
                "X-Import-Skipped, X-Import-Total, Content-Disposition"
            ),
        },
    )


async def read_upload_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    """分块读取上传文件，一超出上限立即中止。

    先 ``await file.read()`` 再判断长度，会把整个文件读进内存后才拒绝，
    上限就失去了保护作用；这里边读边累计，超限直接抛 422。
    """

    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ApiError("导入文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        chunks.append(chunk)
    return b"".join(chunks)


async def read_import_upload(request: Request, max_bytes: int) -> bytes:
    """在权限依赖通过之后再解析 multipart，并按总字节数中止。

    路由参数里的 ``UploadFile`` 会在鉴权之前被框架写进临时文件。调用方应把
    本函数放在路由函数体内，让 ``Depends`` 先执行。没有 Content-Length 时
    也按实际读到的字节计数。
    """

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise ApiError("请上传 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    received = 0
    limit = max_bytes + MULTIPART_OVERHEAD_BYTES

    async def chunks() -> AsyncGenerator[bytes, None]:
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                raise ApiError("导入文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=413)
            yield chunk

    parser = MultiPartParser(
        request.headers,
        chunks(),
        max_files=2,
        max_fields=8,
        max_part_size=max_bytes,
    )
    try:
        form = await parser.parse()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise ApiError("请上传 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        if upload.size is not None and upload.size > max_bytes:
            raise ApiError("导入文件过大", code=ErrorCode.VALIDATION_ERROR, http_status=413)
        return await read_upload_within_limit(upload, max_bytes)
    except MultiPartException as exc:
        raise ApiError("上传表单无效或超过限制", code=ErrorCode.VALIDATION_ERROR, http_status=413) from exc
    finally:
        # Starlette 只在 MultiPartException 时清理。我们的预算异常、取消、
        # 缺字段以及额外文件都必须关闭；同步 close 不会被任务取消再次打断。
        for temporary in parser._files_to_close_on_error:
            temporary.close()
