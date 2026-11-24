"""预览原文 `/content`：本地缓存的 PDF 支持 Range（206 / 416）和 HEAD，每段都重新鉴权；下载永远是原文件。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.errors import PermissionDeniedError
from platform_common.route_audit import iter_api_routes

from app.core import preview_cache, storage
from app.core.database import get_db_session
from app.knowledge.api import content_response
from app.knowledge.api import routes as knowledge_routes
from app.knowledge.application import knowledge, knowledge_preview
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import FULL_ACCESS
from app.main import app
from tests.helpers import no_pdf_tools, preview_settings

ACTOR = Actor(id="u1", name="测试管理员")
BODY = bytes(range(256)) * 4  # 1024 字节，每个位置的值都能对上
ETAG = '"pdf-etag"'


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("items=0-1", None),  # 不认识的单位：忽略，回整份
        ("bytes=0-1,4-5", None),  # 多段：回整份
        ("bytes=0-99", (0, 99)),
        ("bytes=1000-", (1000, 1023)),
        ("bytes=-24", (1000, 1023)),
        ("bytes=-5000", (0, 1023)),  # 后缀超过文件大小：整份
        ("bytes=1000-9999", (1000, 1023)),  # 终点超出：截到文件末尾
        (" bytes = 5-5 ", (5, 5)),
    ],
)
def test_parse_range(header: str | None, expected: tuple[int, int] | None) -> None:
    got = content_response.parse_range(header, len(BODY))
    assert (None if got is None else (got.start, got.end)) == expected


@pytest.mark.parametrize("header", ["bytes=1024-", "bytes=5-4", "bytes=-0", "bytes=-", "bytes=a-b", "bytes=1-2-3"])
def test_parse_range_rejects(header: str) -> None:
    with pytest.raises(content_response.RangeNotSatisfiableError):
        content_response.parse_range(header, len(BODY))


def test_parse_range_on_empty_file() -> None:
    with pytest.raises(content_response.RangeNotSatisfiableError):
        content_response.parse_range("bytes=0-", 0)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[TestClient, list[str], AsyncMock]]:
    """`/content` 打桩成返回本地缓存 PDF；记下每次请求是否过了鉴权依赖。"""

    pdf = tmp_path / "preview.pdf"
    pdf.write_bytes(BODY)
    authorized: list[str] = []

    async def _db():  # type: ignore[no-untyped-def]
        yield None

    def _actor() -> Actor:
        authorized.append("ok")
        return ACTOR

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[knowledge_routes.get_knowledge_access] = lambda: FULL_ACCESS
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name == "actor":
                app.dependency_overrides[dep.call] = _actor

    def _result(*_args: Any, **_kwargs: Any) -> knowledge_preview.FileStreamResult:
        opened = preview_cache.open_pdf(pdf)
        assert opened is not None
        return knowledge_preview.FileStreamResult(
            stream=opened[0],
            filename="方案.pdf",
            media_type="application/pdf",
            content_length=opened[1],
            etag=ETAG,
            ranged=True,
        )

    service = AsyncMock(side_effect=_result)
    monkeypatch.setattr(knowledge_routes.service, "stream_file_content", service)
    try:
        yield TestClient(app), authorized, service
    finally:
        app.dependency_overrides.clear()


def _url() -> str:
    return f"/api/v1/thinktank/knowledge/{uuid.uuid4()}/content"


def test_full_response_advertises_ranges(client: tuple[TestClient, list[str], AsyncMock]) -> None:
    http, _authorized, _service = client
    res = http.get(_url())
    assert res.status_code == 200
    assert res.content == BODY
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["content-length"] == str(len(BODY))
    assert res.headers["etag"] == ETAG
    assert res.headers["cache-control"] == "private, no-cache"
    assert res.headers["vary"] == "Authorization"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["content-disposition"].startswith("inline;")


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [("bytes=0-99", 0, 99), ("bytes=1000-", 1000, 1023), ("bytes=-24", 1000, 1023), ("bytes=10-10", 10, 10)],
)
def test_range_returns_206_slice(
    client: tuple[TestClient, list[str], AsyncMock], header: str, start: int, end: int
) -> None:
    http, _authorized, _service = client
    res = http.get(_url(), headers={"Range": header})
    assert res.status_code == 206
    assert res.content == BODY[start : end + 1]
    assert res.headers["content-range"] == f"bytes {start}-{end}/{len(BODY)}"
    assert res.headers["content-length"] == str(end - start + 1)
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["etag"] == ETAG


@pytest.mark.parametrize("header", ["bytes=2048-", "bytes=9-3", "bytes=x-"])
def test_unsatisfiable_range_returns_416(client: tuple[TestClient, list[str], AsyncMock], header: str) -> None:
    http, _authorized, _service = client
    res = http.get(_url(), headers={"Range": header})
    assert res.status_code == 416
    assert res.headers["content-range"] == f"bytes */{len(BODY)}"
    assert res.content == b""


def test_if_range_mismatch_sends_whole_file(client: tuple[TestClient, list[str], AsyncMock]) -> None:
    http, _authorized, _service = client
    res = http.get(_url(), headers={"Range": "bytes=0-9", "If-Range": '"old"'})
    assert res.status_code == 200 and res.content == BODY
    res = http.get(_url(), headers={"Range": "bytes=0-9", "If-Range": ETAG})
    assert res.status_code == 206 and res.content == BODY[:10]


def test_head_returns_headers_only(client: tuple[TestClient, list[str], AsyncMock]) -> None:
    http, _authorized, _service = client
    res = http.head(_url())
    assert res.status_code == 200
    assert res.content == b""
    assert res.headers["content-length"] == str(len(BODY))
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["etag"] == ETAG
    res = http.head(_url(), headers={"Range": "bytes=0-9"})
    assert res.status_code == 206 and res.headers["content-range"] == f"bytes 0-9/{len(BODY)}"


def test_every_range_request_is_authorized(client: tuple[TestClient, list[str], AsyncMock]) -> None:
    http, authorized, service = client
    url = _url()
    for header in ("bytes=0-255", "bytes=256-511", "bytes=512-"):
        assert http.get(url, headers={"Range": header}).status_code == 206
    assert len(authorized) == 3 and service.await_count == 3  # 每一段都过鉴权、重新判断范围权限

    service.side_effect = PermissionDeniedError("无权查看该资料")
    denied = http.get(url, headers={"Range": "bytes=0-9"})
    assert denied.status_code == 403
    assert "content-range" not in denied.headers


def test_not_modified_and_text_fallback(client: tuple[TestClient, list[str], AsyncMock]) -> None:
    http, _authorized, service = client
    service.side_effect = None
    service.return_value = knowledge_preview.FileStreamResult(
        stream=knowledge.single_chunk_stream(b""), filename="a.pdf", media_type="", etag=ETAG, not_modified=True
    )
    res = http.get(_url(), headers={"If-None-Match": ETAG, "Range": "bytes=0-9"})
    assert res.status_code == 304 and res.headers["etag"] == ETAG

    # 文本摘要不是本地缓存文件：不支持 Range，也不缓存
    service.return_value = knowledge_preview.FileStreamResult(
        stream=knowledge.single_chunk_stream(b"summary"),
        filename="a.pptx.txt",
        media_type="text/plain; charset=utf-8",
        content_length=7,
    )
    res = http.get(_url(), headers={"Range": "bytes=0-1"})
    assert res.status_code == 200 and res.content == b"summary"
    assert res.headers["cache-control"] == "private, no-store"
    assert "accept-ranges" not in res.headers and "etag" not in res.headers


class _Session:
    def __init__(self) -> None:
        self.commit = AsyncMock()


def _pdf_row(size: int) -> KnowledgeFile:
    return KnowledgeFile(
        id=uuid.uuid4(),
        file_name="大文件.pdf",
        file_type="产品",
        industry_type="无",
        file_suffix="PDF",
        file_size_bytes=size,
        storage_path="knowledge/big.pdf",
        content_text="",
    )


async def test_pdf_preview_is_cached_ranged_and_download_stays_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/big.pdf").write_bytes(BODY)
    row = _pdf_row(len(BODY))
    monkeypatch.setattr(knowledge, "get_settings", lambda: preview_settings(tmp_path))
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge.repo, "add_op_log", AsyncMock())
    monkeypatch.setattr(knowledge, "enqueue_event", AsyncMock())
    no_pdf_tools(monkeypatch)
    monkeypatch.setattr(knowledge_preview.pdf_optimize, "_qpdf_binary", lambda: "/usr/bin/qpdf")

    def linearize(args: list[str]) -> None:
        Path(args[-1]).write_bytes(b"LINEAR:" + Path(args[-2]).read_bytes())

    async def fake_qpdf(args: list[str], **_kwargs: Any) -> int:
        await asyncio.to_thread(linearize, args)
        return 0

    monkeypatch.setattr(knowledge_preview.pdf_optimize.subprocess_guard, "run_isolated", fake_qpdf)
    stream_spy = AsyncMock(wraps=storage.stream_object)
    monkeypatch.setattr(storage, "stream_object", stream_spy)

    session = _Session()
    kwargs: dict[str, Any] = {"actor": ACTOR, "access": FULL_ACCESS, "file_id": row.id}
    res = await knowledge.stream_file_content(session, for_download=False, **kwargs)  # type: ignore[arg-type]
    assert res.ranged is True and res.media_type == "application/pdf"
    assert res.etag and knowledge_preview.expected_preview_etag(row) is None  # 要打开缓存才知道 ETag
    assert b"".join([c async for c in res.stream]) == b"LINEAR:" + BODY
    assert session.commit.await_count == 1  # 拉源文件、跑工具前先交还数据库连接

    again = await knowledge.stream_file_content(session, for_download=False, **kwargs)  # type: ignore[arg-type]
    await knowledge.close_file_stream(again)
    assert stream_spy.await_count == 1  # 第二次（以及之后的每段 Range）读本地缓存
    assert again.etag == res.etag

    cached = await knowledge.stream_file_content(
        session,
        for_download=False,
        if_none_match=res.etag,
        **kwargs,  # type: ignore[arg-type]
    )
    assert cached.not_modified is True and cached.etag == res.etag

    # 缓存被淘汰后重做出来的字节不同（gs / qpdf 每次写新的 /ID）：ETag 跟着变，旧副本不再被 304 沿用。
    cache_file = next((tmp_path / "preview_cache").glob("*.pdf"))
    cache_file.write_bytes(b"LINEAR2:" + BODY)
    rebuilt = await knowledge.stream_file_content(
        session,
        for_download=False,
        if_none_match=res.etag,
        **kwargs,  # type: ignore[arg-type]
    )
    await knowledge.close_file_stream(rebuilt)
    assert rebuilt.not_modified is False and rebuilt.etag != res.etag

    download = await knowledge.stream_file_content(session, for_download=True, **kwargs)  # type: ignore[arg-type]
    assert download.ranged is False
    assert b"".join([c async for c in download.stream]) == BODY  # 下载永远是对象存储里的原文件


async def test_pdf_preview_falls_back_to_original_when_cache_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/big.pdf").write_bytes(BODY)
    row = _pdf_row(len(BODY))
    monkeypatch.setattr(knowledge, "get_settings", lambda: preview_settings(tmp_path))
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge_preview.pdf_optimize, "prepare_pdf_preview", AsyncMock(return_value=None))

    res = await knowledge.stream_file_content(
        _Session(),  # type: ignore[arg-type]
        actor=ACTOR,
        access=FULL_ACCESS,
        file_id=row.id,
        for_download=False,
    )
    assert res.ranged is False
    assert b"".join([c async for c in res.stream]) == BODY


async def test_drop_preview_cache_removes_current_and_legacy_entries(tmp_path: Path) -> None:
    row = _pdf_row(10)
    settings = preview_settings(tmp_path)
    cache_dir = tmp_path / "preview_cache"
    cache_dir.mkdir()
    keys = [
        preview_cache.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes, "preview-v2"),
        preview_cache.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes),
    ]
    for key in keys:
        (cache_dir / f"{key}.pdf").write_bytes(b"%PDF")
    await knowledge_preview.drop_preview_cache(settings, row)
    # 只剩两份墓碑（正在做的转换写完缓存后据此删掉自己），PDF 都删了
    assert sorted(p.name for p in cache_dir.iterdir()) == sorted(f"{key}.deleted" for key in keys)
