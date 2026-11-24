"""仓储查询构造、MinIO HTTP 分支、码表省同步与全部 API 路由补充覆盖测试。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes
from sqlalchemy.dialects import postgresql

from app.common import codebook_client
from app.core import storage
from app.core.database import get_db_session
from app.knowledge.api import content_response
from app.knowledge.api import routes as knowledge_routes
from app.knowledge.application import knowledge_preview
from app.knowledge.domain.models import KnowledgeFile, KnowledgeOpLog
from app.knowledge.domain.scopes import FULL_ACCESS, KnowledgeAccess
from app.knowledge.repositories import knowledge as repo
from app.main import app

ACTOR = Actor(id="u1", name="测试用户")
NOW = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)


def _sql_text(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None, scalar_val: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar_val

    def scalars(self) -> list[Any]:
        return self._rows

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _RecordingSession:
    def __init__(self, results: list[Any] | None = None, scalars: list[Any] | None = None) -> None:
        self.stmts: list[Any] = []
        self.added: list[Any] = []
        self._results = list(results or [])
        self._scalars = list(scalars or [])
        self.get = AsyncMock(return_value=None)
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def execute(self, stmt: Any) -> _FakeResult:
        self.stmts.append(stmt)
        if self._results:
            return self._results.pop(0)
        return _FakeResult()

    async def scalar(self, stmt: Any) -> Any:
        self.stmts.append(stmt)
        if self._scalars:
            return self._scalars.pop(0)
        return 0


def test_repo_filter_and_scope_sql_builders() -> None:
    empty_access = KnowledgeAccess(file_type_levels={}, industry_levels={})
    assert _sql_text(repo._industry_scope_condition(frozenset())).lower() == "false"
    assert len(repo._scope_conditions(empty_access)) == 1

    part_access = KnowledgeAccess.from_levels(
        {"thinktank.file_type.product": "READ", "thinktank.industry_type.none": "READ"}
    )
    scope_conds = repo._scope_conditions(part_access)
    assert "thinktank_knowledge_files.industry_type =" in _sql_text(scope_conds[1])

    filters = {
        "file_name": ["专线"],
        "file_type": ["产品", "未定义"],
        "operator_type": ["电信"],
        "prov_name": ["集团"],
        "market_category": ["行客"],
        "product_sub_type": ["智算"],
        "app_scenario": ["医院"],
        "depart_affiliation": ["政企"],
        "data_time": ["2026/6"],
        "product_type": ["网"],
        "industry_type": ["无", "教育"],
        "tag_status": ["已定义"],
        "favorite_only": ["已收藏"],
    }
    conds = repo._conditions(filters, user_id="u1")
    joined = " AND ".join(_sql_text(c) for c in conds)
    assert "thinktank_knowledge_files.file_name ILIKE" in joined
    assert "thinktank_knowledge_files.file_type IN" in joined
    assert "thinktank_knowledge_files.is_defined IS true" in joined
    assert "thinktank_knowledge_favorites.user_id" in joined


async def test_repo_crud_and_options_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    fid = uuid.uuid4()
    row = KnowledgeFile(
        id=fid,
        file_name="测试.pdf",
        file_type="产品",
        uploaded_at=NOW,
        created_at=NOW,
        created_by_id="u1",
        created_by_name="测试",
        updated_at=NOW,
        updated_by_id="u1",
        updated_by_name="测试",
    )
    log_row = KnowledgeOpLog(
        id=uuid.uuid4(),
        file_id=fid,
        actor_id="u1",
        actor_name="测试",
        op_type="预览",
        detail="d",
        created_at=NOW,
    )
    sess = _RecordingSession(
        results=[
            _FakeResult([row]),  # list_items
            _FakeResult([row]),  # list_filtered
            _FakeResult([row]),  # list_undefined
            _FakeResult(scalar_val=row),  # get_by_file_name
            _FakeResult([fid]),  # favorite_ids_for_user
            _FakeResult([log_row]),  # list_op_logs
        ],
        scalars=[1, 1, 1, None, fid, fid, 1],
    )
    sess.get = AsyncMock(return_value=row)  # type: ignore[method-assign]

    items, total = await repo.list_items(sess, filters={}, access=FULL_ACCESS, user_id="u1", page=1, page_size=20)  # type: ignore[arg-type]
    assert len(items) == 1 and total == 1
    assert await repo.count_filtered(sess, {}, access=FULL_ACCESS, user_id="u1") == 1  # type: ignore[arg-type]
    assert len(await repo.list_filtered(sess, {}, access=FULL_ACCESS, user_id="u1")) == 1  # type: ignore[arg-type]
    assert await repo.count_undefined(sess, access=FULL_ACCESS) == 1  # type: ignore[arg-type]
    assert len(await repo.list_undefined(sess, access=FULL_ACCESS)) == 1  # type: ignore[arg-type]
    assert await repo.get_by_id(sess, fid) is row  # type: ignore[arg-type]
    assert await repo.get_for_update(sess, fid) is row  # type: ignore[arg-type]
    assert await repo.get_by_file_name(sess, "测试.pdf") is row  # type: ignore[arg-type]
    assert await repo.favorite_ids_for_user(sess, user_id="u1", file_ids=[]) == set()  # type: ignore[arg-type]
    assert await repo.favorite_ids_for_user(sess, user_id="u1", file_ids=[fid]) == {fid}  # type: ignore[arg-type]
    assert await repo.is_favorited(sess, user_id="u1", file_id=fid) is False  # type: ignore[arg-type]
    assert await repo.set_favorite(sess, user_id="u1", file_id=fid, favorite=True) is True  # type: ignore[arg-type]
    assert await repo.set_favorite(sess, user_id="u1", file_id=fid, favorite=False) is True  # type: ignore[arg-type]
    await repo.add_op_log(sess, file_id=fid, actor_id="u1", actor_name="测试", op_type="预览", detail="x")  # type: ignore[arg-type]
    logs, log_total = await repo.list_op_logs(sess, file_id=fid, page=1, page_size=10)  # type: ignore[arg-type]
    assert len(logs) == 1 and log_total == 1

    monkeypatch.setattr(
        repo, "preview_options", AsyncMock(return_value={"prov_name": {"items": [], "truncated": False}})
    )
    opts = await repo.list_options(sess, access=FULL_ACCESS, provinces=["集团", "北京市"])  # type: ignore[arg-type]
    assert opts["options"]["prov_name"]["items"] == ["集团", "北京市"]
    assert await repo.search_option_values(sess, field="prov_name", keyword="北", provinces=["集团", "北京市"]) == [
        "北京市"
    ]  # type: ignore[arg-type]


class _FakeHttpClient:
    is_closed = False
    calls: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeHttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def aclose(self) -> None:
        self.is_closed = True

    async def put(
        self,
        url: str,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        **_kwargs: Any,
    ) -> httpx.Response:
        self.calls.append(("PUT", url))
        return httpx.Response(200, request=httpx.Request("PUT", url))

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **_kwargs: Any,
    ) -> httpx.Response:
        self.calls.append(("GET", url))
        if "boom" in url:
            raise httpx.ConnectError("refused")
        if "missing" in url:
            return httpx.Response(404, request=httpx.Request("GET", url))
        if "provinces" in url:
            return httpx.Response(
                200, json={"data": {"items": ["上海市", "浙江省"]}}, request=httpx.Request("GET", url)
            )
        return httpx.Response(200, content=b"pdf-bytes", request=httpx.Request("GET", url))

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **_kwargs: Any,
    ) -> httpx.Response:
        self.calls.append(("DELETE", url))
        return httpx.Response(204, request=httpx.Request("DELETE", url))


async def test_minio_http_and_codebook_client_http(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    minio_cfg = SimpleNamespace(
        storage_dir=str(tmp_path),
        minio_endpoint="http://minio.local:8088",
        minio_access_key="ak",
        minio_secret_key="sk",
        minio_bucket="bk",
        minio_region="us-east-1",
        minio_timeout_seconds=5.0,
    )
    _FakeHttpClient.calls = []

    await storage.close_storage_client()
    monkeypatch.setattr(storage.httpx, "AsyncClient", _FakeHttpClient)
    await storage.save_object(minio_cfg, "knowledgeBase/a.pdf", b"pdf-bytes", content_type="application/pdf")
    assert await storage.read_object(minio_cfg, "knowledgeBase/a.pdf") == b"pdf-bytes"
    assert await storage.read_object(minio_cfg, "knowledgeBase/missing.pdf") is None
    with pytest.raises(storage.StorageUnavailableError):
        await storage.read_object(minio_cfg, "knowledgeBase/boom.pdf", raise_on_error=True)
    await storage.delete_object(minio_cfg, "knowledgeBase/a.pdf")
    await storage.close_storage_client()
    assert [m for m, _ in _FakeHttpClient.calls] == ["PUT", "GET", "GET", "GET", "DELETE"]

    monkeypatch.setattr(codebook_client.httpx, "AsyncClient", _FakeHttpClient)
    codebook_client.clear_province_cache()
    cb_cfg = SimpleNamespace(
        codebook_base_url="http://codebook:8004", codebook_service_secret="sec", codebook_timeout_seconds=1.0
    )
    assert await codebook_client.get_provinces(cb_cfg, ("集团",)) == ["集团", "上海市", "浙江省"]
    # 命中缓存
    assert await codebook_client.get_provinces(cb_cfg, ("集团",)) == ["集团", "上海市", "浙江省"]
    # 连接失败回退兜底
    codebook_client.clear_province_cache()
    bad_cfg = SimpleNamespace(
        codebook_base_url="http://boom:8004", codebook_service_secret="sec", codebook_timeout_seconds=1.0
    )
    assert await codebook_client.get_provinces(bad_cfg, ("集团", "北京市")) == ["集团", "北京市"]


def test_content_disposition_sanitizes_header_chars() -> None:
    header = content_response.content_disposition("attachment", 'bad"\r\nname.pdf')
    assert "\r" not in header and "\n" not in header
    assert 'filename="bad___name.pdf"' in header


def test_remaining_http_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[knowledge_routes.get_knowledge_access] = lambda: FULL_ACCESS
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"actor", "_"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR

    fid = uuid.uuid4()
    monkeypatch.setattr(knowledge_routes.export_import, "export_filtered_excel", AsyncMock(return_value=b"xlsx"))
    monkeypatch.setattr(knowledge_routes.export_import, "export_undefined_excel", AsyncMock(return_value=b"undef-xlsx"))
    monkeypatch.setattr(
        knowledge_routes.write_service, "upload_knowledge_file", AsyncMock(return_value={"id": str(fid)})
    )
    monkeypatch.setattr(
        knowledge_routes.export_import,
        "upload_knowledge_tags",
        AsyncMock(
            return_value={
                "total": 1,
                "inserted": 0,
                "updated": 1,
                "skipped": 0,
                "rejected": False,
                "skipped_file": None,
            }
        ),
    )
    monkeypatch.setattr(knowledge_routes.service, "get_detail", AsyncMock(return_value={"id": str(fid)}))
    monkeypatch.setattr(
        knowledge_routes.service,
        "preview_knowledge",
        AsyncMock(return_value={"item": {"id": str(fid)}, "preview": {"mode": "pdf"}}),
    )

    async def _pdf_stream():  # type: ignore[no-untyped-def]
        yield b"%PDF"

    monkeypatch.setattr(
        knowledge_routes.service,
        "stream_file_content",
        AsyncMock(
            return_value=knowledge_preview.FileStreamResult(
                stream=_pdf_stream(), filename="a.pdf", media_type="application/pdf", content_length=4
            )
        ),
    )
    monkeypatch.setattr(
        knowledge_routes.service, "toggle_favorite", AsyncMock(return_value={"id": str(fid), "is_favorited": False})
    )
    monkeypatch.setattr(
        knowledge_routes.service,
        "list_logs",
        AsyncMock(return_value={"items": [], "total": 0, "page": 1, "page_size": 10}),
    )
    monkeypatch.setattr(
        knowledge_routes.write_service, "update_metadata", AsyncMock(return_value={"id": str(fid), "version": 2})
    )
    monkeypatch.setattr(
        knowledge_routes.write_service, "delete_knowledge_file", AsyncMock(return_value={"deleted": True})
    )

    try:
        client = TestClient(app)
        assert client.get("/api/v1/thinktank/knowledge/export").status_code == 200
        assert client.get("/api/v1/thinktank/knowledge/export-undefined").status_code == 200
        assert (
            client.post(
                "/api/v1/thinktank/knowledge/upload", files={"file": ("demo.pdf", b"%PDF", "application/pdf")}
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/thinktank/knowledge/upload-tags",
                files={
                    "file": (
                        "tags.xlsx",
                        b"PK\x03\x04",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/thinktank/knowledge/{fid}").status_code == 200
        assert client.get(f"/api/v1/thinktank/knowledge/{fid}/preview").status_code == 200
        content = client.get(f"/api/v1/thinktank/knowledge/{fid}/content")
        assert content.status_code == 200
        # 无 ETag 的摘要兜底仍走 no-store
        assert content.headers["cache-control"] == "private, no-store"

        monkeypatch.setattr(
            knowledge_routes.service,
            "stream_file_content",
            AsyncMock(
                return_value=knowledge_preview.FileStreamResult(
                    stream=_pdf_stream(),
                    filename="a.pdf",
                    media_type="application/pdf",
                    content_length=4,
                    etag='"demo-etag"',
                )
            ),
        )
        cached = client.get(f"/api/v1/thinktank/knowledge/{fid}/content")
        assert cached.status_code == 200
        assert cached.headers["etag"] == '"demo-etag"'
        assert cached.headers["cache-control"] == "private, no-cache"
        assert cached.headers["vary"] == "Authorization"

        monkeypatch.setattr(
            knowledge_routes.service,
            "stream_file_content",
            AsyncMock(
                return_value=knowledge_preview.FileStreamResult(
                    stream=_pdf_stream(),
                    filename="a.pdf",
                    media_type="",
                    etag='"demo-etag"',
                    not_modified=True,
                )
            ),
        )
        not_mod = client.get(f"/api/v1/thinktank/knowledge/{fid}/content", headers={"If-None-Match": '"demo-etag"'})
        assert not_mod.status_code == 304
        assert not_mod.headers["etag"] == '"demo-etag"'
        assert not_mod.headers["cache-control"] == "private, no-cache"
        assert not_mod.headers["vary"] == "Authorization"
        assert client.delete(f"/api/v1/thinktank/knowledge/{fid}/favorite").json()["data"]["is_favorited"] is False
        assert client.get(f"/api/v1/thinktank/knowledge/{fid}/logs").status_code == 200
        assert (
            client.patch(f"/api/v1/thinktank/knowledge/{fid}", json={"version": 1, "remark": "ok"}).status_code == 200
        )
        assert client.delete(f"/api/v1/thinktank/knowledge/{fid}").json()["data"]["deleted"] is True
    finally:
        app.dependency_overrides.clear()
