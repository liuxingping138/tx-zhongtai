from __future__ import annotations

import base64
from typing import Any

from fastapi.responses import JSONResponse, Response
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse


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
