"""上传后后台预热预览缓存：开关、跳过条件、失败不影响上传。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.route_audit import iter_api_routes

from app.core import office_preview, preview_cache, preview_slots
from app.core.database import get_db_session
from app.knowledge.api import routes as knowledge_routes
from app.knowledge.application import knowledge_preview, preview_warmup
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import FULL_ACCESS
from app.main import app
from tests.helpers import no_pdf_tools, preview_settings

ACTOR = Actor(id="u1", name="测试管理员")


def _row(file_name: str = "方案.pdf", suffix: str = "PDF", storage_path: str = "k/a.pdf") -> KnowledgeFile:
    return KnowledgeFile(
        id=uuid.uuid4(),
        file_name=file_name,
        file_suffix=suffix,
        storage_path=storage_path,
        file_size_bytes=8,
    )


def _factory(row: KnowledgeFile | None, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(preview_warmup.repo, "get_by_id", AsyncMock(return_value=row))

    @asynccontextmanager
    async def _session() -> AsyncIterator[None]:
        yield None

    return _session


def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    settings = preview_settings(tmp_path)
    monkeypatch.setattr(preview_warmup, "get_settings", lambda: settings)
    return settings


def _logs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []
    fake = SimpleNamespace(
        info=lambda event, **kw: seen.append((event, kw)),
        warning=lambda event, **kw: seen.append((event, kw)),
    )
    monkeypatch.setattr(preview_warmup, "logger", fake)
    return seen


def test_schedule_respects_toggle() -> None:
    file_id = str(uuid.uuid4())
    on = BackgroundTasks()
    assert preview_warmup.schedule_upload_warmup(on, SimpleNamespace(preview_warmup_on_upload=True), file_id) is True
    assert len(on.tasks) == 1
    assert on.tasks[0].args == (uuid.UUID(file_id),)
    off = BackgroundTasks()
    assert preview_warmup.schedule_upload_warmup(off, SimpleNamespace(preview_warmup_on_upload=False), file_id) is False
    assert off.tasks == []


async def test_warm_pdf_fills_cache_and_logs_done(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, monkeypatch)
    no_pdf_tools(monkeypatch)
    row = _row()
    source = tmp_path / "source.pdf"
    await asyncio.to_thread(source.write_bytes, b"%PDF-1.7")

    async def _stream(_settings: Any, _path: str) -> tuple[AsyncIterator[bytes], int]:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"%PDF-1.7"

        return chunks(), 8

    monkeypatch.setattr(knowledge_preview.storage, "stream_object", _stream)
    logs = _logs(monkeypatch)
    await preview_warmup.warm_preview(row.id, session_factory=_factory(row, monkeypatch))
    assert logs == [("preview_warmup_done", {"file_id": str(row.id)})]
    key = preview_cache.cache_key_for(str(row.id), row.storage_path, row.file_size_bytes, "preview-v2")
    cached = preview_cache.pdf_path(str(Path(settings.storage_dir) / "preview_cache"), key)
    assert await asyncio.to_thread(cached.is_file)

    # 再预热一次：已有缓存直接跳过，不再拉源文件
    monkeypatch.setattr(knowledge_preview.storage, "stream_object", AsyncMock(side_effect=AssertionError("不该再拉")))
    await preview_warmup.warm_preview(row.id, session_factory=_factory(row, monkeypatch))
    assert logs[-1] == ("preview_warmup_skipped", {"file_id": str(row.id), "reason": "cached"})


@pytest.mark.parametrize(
    ("row", "patches", "reason"),
    [
        (None, {}, "deleted"),
        (_row(storage_path=""), {}, "no_source"),
        (_row("说明.txt", "TXT", "k/a.txt"), {}, "not_previewable"),
        (_row("方案.pptx", "PPTX", "k/a.pptx"), {"has_libreoffice": False}, "no_libreoffice"),
        (_row("方案.pptx", "PPTX", "k/a.pptx"), {"has_libreoffice": True, "busy": True}, "busy"),
        (_row(), {"busy": True}, "busy"),
    ],
)
async def test_warm_skips(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: KnowledgeFile | None,
    patches: dict[str, bool],
    reason: str,
) -> None:
    _settings(tmp_path, monkeypatch)
    monkeypatch.setattr(office_preview, "has_libreoffice", lambda: patches.get("has_libreoffice", False))
    monkeypatch.setattr(preview_slots, "has_free_slot", lambda: not patches.get("busy", False))
    opened = AsyncMock()
    monkeypatch.setattr(preview_warmup, "open_preview_pdf", opened)
    logs = _logs(monkeypatch)
    file_id = row.id if row is not None else uuid.uuid4()
    await preview_warmup.warm_preview(file_id, session_factory=_factory(row, monkeypatch))
    assert logs == [("preview_warmup_skipped", {"file_id": str(file_id), "reason": reason})]
    opened.assert_not_awaited()


async def test_warm_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _settings(tmp_path, monkeypatch)
    row = _row()
    logs = _logs(monkeypatch)
    monkeypatch.setattr(preview_warmup, "open_preview_pdf", AsyncMock(side_effect=RuntimeError("存储断了")))
    await preview_warmup.warm_preview(row.id, session_factory=_factory(row, monkeypatch))
    assert logs == [("preview_warmup_failed", {"file_id": str(row.id), "error": "存储断了"})]

    monkeypatch.setattr(preview_warmup, "open_preview_pdf", AsyncMock(return_value=None))
    await preview_warmup.warm_preview(row.id, session_factory=_factory(row, monkeypatch))
    assert logs[-1] == ("preview_warmup_failed", {"file_id": str(row.id), "error": "preview_unavailable"})


def _client_with_upload(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> tuple[TestClient, str]:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    file_id = str(uuid.uuid4())
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[knowledge_routes.get_knowledge_access] = lambda: FULL_ACCESS
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"actor", "_"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR
    settings = knowledge_routes.get_settings().model_copy(update={"preview_warmup_on_upload": enabled})
    app.dependency_overrides[knowledge_routes.get_settings] = lambda: settings
    monkeypatch.setattr(
        knowledge_routes.write_service,
        "upload_knowledge_file",
        AsyncMock(return_value={"id": file_id, "file_name": "方案.pdf"}),
    )
    return TestClient(app, headers={"Authorization": "Bearer test"}), file_id


@pytest.mark.parametrize("enabled", [True, False])
def test_upload_route_schedules_warmup_by_toggle(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    warmed: list[uuid.UUID] = []

    async def _warm(file_id: uuid.UUID) -> None:
        warmed.append(file_id)

    monkeypatch.setattr(preview_warmup, "warm_preview", _warm)
    try:
        client, file_id = _client_with_upload(monkeypatch, enabled)
        res = client.post("/api/v1/thinktank/knowledge/upload", files={"file": ("方案.pdf", b"%PDF-1.7")})
        assert res.status_code == 201
        assert warmed == ([uuid.UUID(file_id)] if enabled else [])
    finally:
        app.dependency_overrides.clear()


def test_upload_succeeds_when_warmup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # 真正的 warm_preview：内部出错只记日志，上传照常 201
    monkeypatch.setattr(preview_warmup, "_warm", AsyncMock(side_effect=RuntimeError("转码进程崩了")))
    logs = _logs(monkeypatch)
    try:
        client, file_id = _client_with_upload(monkeypatch, True)
        res = client.post("/api/v1/thinktank/knowledge/upload", files={"file": ("方案.pdf", b"%PDF-1.7")})
        assert res.status_code == 201
        assert res.json()["data"]["id"] == file_id
        assert logs == [("preview_warmup_failed", {"file_id": file_id, "error": "转码进程崩了"})]
    finally:
        app.dependency_overrides.clear()
