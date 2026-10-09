import asyncio
from unittest.mock import patch

import pytest
import starlette.formparsers as parsers
from platform_common.errors import ApiError
from platform_common.http_utils import read_import_upload
from starlette.datastructures import Headers


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["limit", "cancel", "missing", "extra", "valid"])
async def test_all_upload_files_closed_on_every_exit(mode):
    files = []
    real = parsers.SpooledTemporaryFile
    reached_tail = False

    def capture(*args, **kwargs):
        file = real(*args, **kwargs)
        files.append(file)
        return file

    class Request:
        headers = Headers({"content-type": "multipart/form-data; boundary=x"})

        async def stream(self):
            nonlocal reached_tail
            field = "other" if mode == "missing" else "file"
            yield (f'--x\r\nContent-Disposition: form-data; name="{field}"; filename="a.xlsx"\r\n\r\n').encode()
            yield b"a" * (1100 * 1024)
            if mode == "limit":
                yield b"b" * (300 * 1024)
                reached_tail = True
                raise AssertionError("超限以后不能继续读取")
            if mode == "cancel":
                raise asyncio.CancelledError()
            if mode == "extra":
                yield b'\r\n--x\r\nContent-Disposition: form-data; name="extra"; filename="b.xlsx"\r\n\r\nb'
            yield b"\r\n--x--\r\n"

    with patch.object(parsers, "SpooledTemporaryFile", capture):
        if mode == "limit":
            with pytest.raises(ApiError) as exc:
                await read_import_upload(Request(), 1024 * 1024)
            assert exc.value.http_status == 413
            assert not reached_tail
        elif mode == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await read_import_upload(Request(), 2 * 1024 * 1024)
        elif mode == "missing":
            with pytest.raises(ApiError, match="请上传"):
                await read_import_upload(Request(), 2 * 1024 * 1024)
        else:
            result = await read_import_upload(Request(), 2 * 1024 * 1024)
            assert len(result) == 1100 * 1024
    assert files and all(file.closed for file in files)
    assert len(files) == (2 if mode == "extra" else 1)
