"""上传体积限制与 Excel 线程池包装的回归测试。"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import load_workbook
from platform_common.errors import ApiError
from platform_common.excel import (
    build_workbook,
    build_workbook_async,
    encode_skipped_file_async,
    parse_sheet_async,
)
from platform_common.http_utils import read_upload_within_limit

from app.policy.domain.fields import SOURCE_COLUMNS


def _upload(payload: bytes) -> UploadFile:
    return UploadFile(filename="t.xlsx", file=io.BytesIO(payload))


def _cells(payload: bytes) -> list[tuple[object, ...]]:
    sheet = load_workbook(io.BytesIO(payload)).active
    assert sheet is not None
    return [tuple(row) for row in sheet.iter_rows(values_only=True)]


def test_read_upload_accepts_file_at_limit() -> None:
    payload = b"x" * 1000
    content = asyncio.run(read_upload_within_limit(_upload(payload), 1000))
    assert content == payload


def test_read_upload_rejects_oversized_file() -> None:
    with pytest.raises(ApiError) as exc:
        asyncio.run(read_upload_within_limit(_upload(b"x" * 1001), 1000))
    assert exc.value.http_status == 422
    assert "过大" in exc.value.message


def test_read_upload_stops_before_buffering_whole_file() -> None:
    """超限时必须在读完整个文件前就中止，否则上限起不到保护作用。"""

    class CountingUpload:
        def __init__(self, total: int) -> None:
            self.remaining = total
            self.read_bytes = 0

        async def read(self, size: int = -1) -> bytes:
            chunk = b"x" * min(size, self.remaining)
            self.remaining -= len(chunk)
            self.read_bytes += len(chunk)
            return chunk

    upload = CountingUpload(64 * 1024 * 1024)
    with pytest.raises(ApiError):
        asyncio.run(read_upload_within_limit(upload, 1024 * 1024))  # type: ignore[arg-type]
    # 只多读了一个分块就停下，而不是把 64MB 全读进内存。
    assert upload.read_bytes <= 2 * 1024 * 1024


def test_excel_async_wrappers_match_sync_results() -> None:
    rows = [{spec.field: "值" for spec in SOURCE_COLUMNS} | {"created_at": None, "updated_at": None}]

    async def run() -> None:
        payload = await build_workbook_async(SOURCE_COLUMNS, rows, sheet_name="网站编码")
        # xlsx 里带精确到秒的创建时间，两次生成跨秒字节就不同；比内容，不比字节。
        expected = build_workbook(SOURCE_COLUMNS, rows, sheet_name="网站编码")
        assert _cells(payload) == _cells(expected)

        parsed = await parse_sheet_async(payload, SOURCE_COLUMNS, subject="政策")
        assert len(parsed) == 1
        assert parsed[0]["site_name"] == "值"

        assert await encode_skipped_file_async(SOURCE_COLUMNS, []) is None
        assert await encode_skipped_file_async(SOURCE_COLUMNS, rows)

    asyncio.run(run())


def test_parse_sheet_async_propagates_api_error() -> None:
    """线程池里抛出的业务异常要原样传回，而不是变成 500。"""

    with pytest.raises(ApiError) as exc:
        asyncio.run(parse_sheet_async(b"not an xlsx", SOURCE_COLUMNS))
    assert exc.value.http_status == 422


def test_excel_async_does_not_block_event_loop() -> None:
    """导出期间事件循环必须还能调度其他任务。"""

    rows = [
        {spec.field: f"值{i}" for spec in SOURCE_COLUMNS} | {"created_at": None, "updated_at": None}
        for i in range(8000)
    ]

    async def run() -> int:
        ticks = 0

        async def heartbeat() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        await build_workbook_async(SOURCE_COLUMNS, rows, sheet_name="网站编码")
        beat.cancel()
        return ticks

    # 同步版本会把循环整个占住，心跳一次都跑不了。
    assert asyncio.run(run()) > 0
