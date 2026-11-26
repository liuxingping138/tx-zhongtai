"""统一响应与导入上传：响应头、边读边限流、没有文件或超限时的拒绝。"""

from __future__ import annotations

import base64
import io
from urllib.parse import quote

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from platform_common.errors import ApiError, register_exception_handlers
from platform_common.http_utils import (
    content_disposition,
    import_result_response,
    read_import_upload,
    read_upload_within_limit,
    success_json,
)


def test_success_json_wraps_data_in_the_standard_envelope() -> None:
    body = json_of(success_json({"a": 1}, status_code=201))
    assert body["code"] == "OK" and body["data"] == {"a": 1}


def json_of(response) -> dict:  # type: ignore[no-untyped-def]
    import json

    return json.loads(response.body)


class TestImportResponse:
    def test_without_a_skipped_file_it_is_plain_json_minus_the_file(self) -> None:
        response = import_result_response({"inserted": 2, "skipped_file": None}, "x.xlsx")
        assert response.media_type == "application/json"
        assert json_of(response)["data"] == {"inserted": 2}

    def test_with_a_skipped_file_the_counts_travel_in_headers(self) -> None:
        raw = base64.b64encode(b"xlsx-bytes").decode()
        response = import_result_response(
            {"skipped_file": raw, "rejected": True, "inserted": 0, "updated": 1, "skipped": 3, "total": 4}, "x.xlsx"
        )
        assert response.body == b"xlsx-bytes"
        assert response.headers["X-Import-Rejected"] == "1"
        assert (response.headers["X-Import-Inserted"], response.headers["X-Import-Skipped"]) == ("0", "3")
        assert "X-Import-Total" in response.headers["Access-Control-Expose-Headers"]
        assert 'filename="x.xlsx"' in response.headers["Content-Disposition"]

    def test_raw_bytes_are_accepted_too(self) -> None:
        response = import_result_response({"skipped_file": b"raw", "total": 1}, "x.xlsx")
        assert response.body == b"raw" and response.headers["X-Import-Rejected"] == "0"

    def test_chinese_filename_is_latin1_safe_with_rfc5987_utf8(self) -> None:
        filename = "知识标签-跳过明细.xlsx"
        response = import_result_response({"skipped_file": b"xlsx", "skipped": 1, "total": 1}, filename)
        header = response.headers["Content-Disposition"]
        header.encode("latin-1")
        assert 'filename="import-result.xlsx"' in header
        assert f"filename*=UTF-8''{quote(filename, safe='')}" in header

        app = FastAPI()

        @app.post("/upload-tags")
        def _upload() -> Response:
            return import_result_response({"skipped_file": b"xlsx", "skipped": 1, "total": 1}, filename)

        res = TestClient(app).post("/upload-tags")
        assert res.status_code == 200
        assert res.content == b"xlsx"
        assert f"filename*=UTF-8''{quote(filename, safe='')}" in res.headers["content-disposition"]

    def test_content_disposition_encodes_slash_and_keeps_extension_on_non_ascii(self) -> None:
        header = content_disposition("inline", "工作报告.pdf", fallback="knowledge-file")
        header.encode("latin-1")
        assert 'filename="knowledge-file.pdf"' in header
        assert f"filename*=UTF-8''{quote('工作报告.pdf', safe='')}" in header

        slashed = content_disposition("attachment", "dir/report.pdf", fallback="knowledge-file")
        assert "%2F" in slashed
        assert "/" not in slashed.split("filename*=UTF-8''", 1)[1]


class TestReadUploadWithinLimit:
    async def test_small_file_is_read_whole(self) -> None:
        upload = UploadFile(io.BytesIO(b"x" * 10), filename="a.xlsx")
        assert await read_upload_within_limit(upload, 100) == b"x" * 10

    async def test_stops_as_soon_as_the_limit_is_crossed(self) -> None:
        upload = UploadFile(io.BytesIO(b"x" * 101), filename="a.xlsx")
        with pytest.raises(ApiError, match="过大"):
            await read_upload_within_limit(upload, 100)


def _app(limit: int) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/import")
    async def upload(request: Request) -> dict[str, int]:
        return {"size": len(await read_import_upload(request, limit))}

    return TestClient(app, raise_server_exceptions=False)


class TestReadImportUpload:
    def test_accepts_a_multipart_file(self) -> None:
        response = _app(1000).post("/import", files={"file": ("a.xlsx", b"x" * 50)})
        assert response.status_code == 200 and response.json() == {"size": 50}

    def test_non_multipart_body_is_refused(self) -> None:
        response = _app(1000).post("/import", json={"file": "x"})
        assert response.status_code == 422 and "请上传 Excel" in response.text

    def test_missing_file_field_is_refused(self) -> None:
        response = _app(1000).post("/import", data={"other": "x"}, files={"other_file": ("a.xlsx", b"x")})
        assert response.status_code == 422

    def test_oversized_file_is_refused(self) -> None:
        response = _app(100).post("/import", files={"file": ("a.xlsx", b"x" * 500)})
        assert response.status_code in {413, 422}
        assert "过大" in response.text or "限制" in response.text
