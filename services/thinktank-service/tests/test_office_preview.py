"""Office 文档转 PDF 在线预览与磁盘缓存单元测试。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError

from app.core import office_preview, storage
from app.knowledge.application import knowledge
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import FULL_ACCESS

ACTOR = Actor(id="u-1", name="测试用户")
NOW = datetime(2026, 11, 20, 4, 0, tzinfo=UTC)


class _Session:
    async def commit(self) -> None:
        return None


def _pptx_row() -> KnowledgeFile:
    return KnowledgeFile(
        id=uuid.uuid4(),
        file_name="河北联通政企年终会-政企部-2026.1.pptx",
        file_type="工作会",
        operator_type="联通",
        depart_affiliation="政企部",
        industry_type="党政",
        app_scenario="无",
        market_category="行客",
        product_type="解决方案",
        product_sub_type="",
        prov_name="河北省",
        data_time="2026.1",
        uploaded_at=NOW,
        file_suffix="PPT",
        file_size_bytes=12345,
        storage_path="knowledgeBase/sample.pptx",
        content_text="",
        remark="",
        is_defined=True,
        version=1,
        created_at=NOW,
        created_by_id="u-1",
        created_by_name="测试用户",
        updated_at=NOW,
        updated_by_id="u-1",
        updated_by_name="测试用户",
    )


def test_office_extension_and_cache_key() -> None:
    assert office_preview.office_extension("年终会.pptx", "PPT") == "PPTX"
    assert office_preview.office_extension("无后缀文件名", "WORD") == "DOCX"
    assert office_preview.office_extension("无后缀文件名", "EXCEL") == "XLSX"
    assert office_preview.office_extension("报告.pdf", "PDF") is None
    assert office_preview.office_extension("说明.txt", "TXT") is None

    k1 = office_preview.cache_key_for("id-1", "knowledgeBase/a.pptx", 100)
    k2 = office_preview.cache_key_for("id-1", "knowledgeBase/a.pptx", 100)
    k3 = office_preview.cache_key_for("id-1", "knowledgeBase/a.pptx", 200)
    assert k1 == k2 and k1 != k3


async def test_convert_office_to_pdf_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = str(tmp_path / "cache")

    # 1. 未安装 LibreOffice 时平滑返回 None
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: None)
    assert await office_preview.convert_office_to_pdf(b"pptx", "PPTX", cache_dir=cache_dir, cache_key="k1") is None

    # 2. 转换成功并写入磁盘缓存，第二次直接命中缓存不再调用子进程
    run_mock = AsyncMock(return_value=b"%PDF-1.4 converted")
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_preview, "_run_soffice", run_mock)
    pdf1 = await office_preview.convert_office_to_pdf(b"pptx", "PPTX", cache_dir=cache_dir, cache_key="k2")
    assert pdf1 == b"%PDF-1.4 converted"
    assert run_mock.await_count == 1

    pdf2 = await office_preview.convert_office_to_pdf(b"pptx", "PPTX", cache_dir=cache_dir, cache_key="k2")
    assert pdf2 == b"%PDF-1.4 converted"
    assert run_mock.await_count == 1
    assert await office_preview.read_cached_pdf(cache_dir, "k2") == b"%PDF-1.4 converted"

    # 3. 转换失败返回 None
    monkeypatch.setattr(office_preview, "_run_soffice", AsyncMock(return_value=None))
    assert await office_preview.convert_office_to_pdf(b"pptx", "PPTX", cache_dir=cache_dir, cache_key="k3") is None


async def test_run_soffice_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "source.pptx"
    src.write_bytes(b"pptx")
    profile = tmp_path / "profile"

    class _OkProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            (tmp_path / "source.pdf").write_bytes(b"%PDF-ok")
            return b"", b""

    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=_OkProc()))
    assert await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 10.0) == b"%PDF-ok"

    class _FailProc:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"convert error"

    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=_FailProc()))
    assert await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 10.0) is None

    class _TimeoutProc:
        returncode = -9
        killed = False

        async def communicate(self) -> tuple[bytes, bytes]:
            raise TimeoutError

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            return -9

    tproc = _TimeoutProc()
    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=tproc))
    assert await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 0.1) is None
    assert tproc.killed is True


async def test_stream_office_preview_cache_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    row = _pptx_row()
    monkeypatch.setattr(knowledge, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge.repo, "is_favorited", AsyncMock(return_value=False))
    monkeypatch.setattr(knowledge.repo, "add_op_log", AsyncMock())
    monkeypatch.setattr(knowledge, "enqueue_event", AsyncMock())
    monkeypatch.setattr(office_preview, "has_libreoffice", lambda: True)

    # 1. preview_knowledge 返回 mode="pdf"
    session: Any = _Session()
    preview_res = await knowledge.preview_knowledge(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id)
    assert preview_res["preview"]["mode"] == "pdf"

    # 2. 缓存未命中 -> 拉 MinIO -> 转 PDF -> 返回 application/pdf
    read_mock = AsyncMock(return_value=b"pptx-raw")
    monkeypatch.setattr(storage, "read_object", read_mock)
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_preview, "_run_soffice", AsyncMock(return_value=b"%PDF-1.4 pptx"))
    res = await knowledge.read_file_content(
        session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, for_download=False
    )
    assert res.media_type == "application/pdf"
    assert res.filename.endswith(".pdf")
    assert res.content == b"%PDF-1.4 pptx"
    assert read_mock.await_count == 1

    # 3. 二次预览直接命中磁盘缓存，不再访问 MinIO
    res2 = await knowledge.read_file_content(
        session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, for_download=False
    )
    assert res2.content == b"%PDF-1.4 pptx"
    assert read_mock.await_count == 1

    # 4. 存储异常返回 503
    row2 = _pptx_row()
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row2))
    monkeypatch.setattr(storage, "read_object", AsyncMock(side_effect=storage.StorageUnavailableError("down")))
    with pytest.raises(ApiError) as exc_info:
        await knowledge.read_file_content(session, actor=ACTOR, access=FULL_ACCESS, file_id=row2.id, for_download=False)
    assert exc_info.value.http_status == 503
