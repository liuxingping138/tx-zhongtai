"""上传体积限制与 Excel 线程池包装的回归测试。"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from platform_common.errors import ApiError

from app.application.excel import build_workbook, build_workbook_async, parse_sheet_async
from app.core.http_utils import read_upload_within_limit
from app.domain.fields import POLICY_TYPE_COLUMNS


def _upload(payload: bytes) -> UploadFile:
    return UploadFile(filename="t.xlsx", file=io.BytesIO(payload))


def test_read_upload_accepts_file_at_limit() -> None:
    payload = b"x" * 1000
    assert asyncio.run(read_upload_within_limit(_upload(payload), 1000)) == payload


def test_read_upload_rejects_oversized_file() -> None:
    with pytest.raises(ApiError) as exc:
        asyncio.run(read_upload_within_limit(_upload(b"x" * 1001), 1000))
    assert exc.value.http_status == 422


def test_excel_async_wrappers_match_sync_results() -> None:
    rows = [{spec.field: "值" for spec in POLICY_TYPE_COLUMNS} | {"created_at": None, "updated_at": None}]

    async def run() -> None:
        payload = await build_workbook_async(POLICY_TYPE_COLUMNS, rows, sheet_name="政策类型枚举值")
        assert payload == build_workbook(POLICY_TYPE_COLUMNS, rows, sheet_name="政策类型枚举值")
        assert len(await parse_sheet_async(payload, POLICY_TYPE_COLUMNS)) == 1

    asyncio.run(run())


def test_parse_sheet_async_propagates_api_error() -> None:
    with pytest.raises(ApiError) as exc:
        asyncio.run(parse_sheet_async(b"not an xlsx", POLICY_TYPE_COLUMNS))
    assert exc.value.http_status == 422
