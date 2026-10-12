"""未通过鉴权的上传不能先把文件写入临时区。流式正文超限时中止。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from platform_common.errors import UnauthenticatedError
from platform_common.route_audit import iter_api_routes
from starlette.datastructures import Headers, UploadFile

from app.core.database import get_db_session
from app.main import app


async def _db():  # type: ignore[no-untyped-def]
    yield None


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_unauthenticated_import_does_not_write_upload() -> None:
    route = next(item for item in iter_api_routes(app) if item.path == "/api/v1/policy/interpretations/import")
    state = {"written": 0}

    async def deny():  # type: ignore[no-untyped-def]
        raise UnauthenticatedError()

    app.dependency_overrides[get_db_session] = _db
    for dep in route.dependant.dependencies:
        if dep.name == "actor":
            app.dependency_overrides[dep.call] = deny
    original = UploadFile.write

    async def counted(self, data):  # type: ignore[no-untyped-def]
        state["written"] += len(data)
        return await original(self, data)

    payload = b"x" * (64 * 1024)
    with patch.object(UploadFile, "write", counted):
        response = TestClient(app).post(
            route.path,
            files={
                "file": (
                    "oversize.xlsx",
                    payload,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers={"Authorization": "Bearer not-a-session"},
        )
    assert response.status_code == 401
    assert state["written"] == 0


def test_missing_bearer_is_rejected_before_the_app_reads() -> None:
    response = TestClient(app).post(
        "/api/v1/policy/interpretations/import",
        files={"file": ("a.xlsx", b"abc", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chunked_upload_stops_at_byte_limit() -> None:
    from platform_common.errors import ApiError
    from platform_common.http_utils import read_import_upload

    boundary = "bound"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="a.xlsx"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + (b"z" * 3000)
        + f"\r\n--{boundary}--\r\n".encode()
    )
    chunks = [body[:10], body[10:40], body[40:]]

    class _Request:
        headers = Headers({"content-type": f"multipart/form-data; boundary={boundary}"})

        async def stream(self):  # type: ignore[no-untyped-def]
            for chunk in chunks:
                yield chunk

    with pytest.raises(ApiError, match="导入文件过大") as raised:
        await read_import_upload(_Request(), 100)  # type: ignore[arg-type]
    assert raised.value.http_status == 413
