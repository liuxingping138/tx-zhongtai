from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse


def success_json(data: Any = None, *, status_code: int = 200, message: str = "success") -> JSONResponse:
    body = ApiResponse(code="OK", message=message, data=data, request_id=get_request_id())
    return JSONResponse(status_code=status_code, content=body.model_dump())
