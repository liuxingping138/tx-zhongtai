"""Office 文档转 PDF 在线预览与磁盘缓存单元测试。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError

from app.core import office_preview, preview_cache, storage
from app.knowledge.application import knowledge
from app.knowledge.domain.models import KnowledgeFile
from app.knowledge.domain.scopes import FULL_ACCESS

ACTOR = Actor(id="u-1", name="测试用户")
NOW = datetime(2026, 11, 20, 4, 0, tzinfo=UTC)


class _Session:
    def __init__(self) -> None:
        self.commit = AsyncMock()


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
    # 文件名没有扩展名时按格式列原样用，旧版 PPT 不会被当成 PPTX
    assert office_preview.office_extension("无后缀文件名", "PPT") == "PPT"
    assert office_preview.office_extension("无后缀文件名", "WORD") == "DOCX"
    assert office_preview.office_extension("无后缀文件名", "EXCEL") == "XLSX"
    assert office_preview.office_extension("报告.pdf", "PDF") is None
    assert office_preview.office_extension("说明.txt", "TXT") is None

    k1 = preview_cache.cache_key_for("id-1", "knowledgeBase/a.pptx", 100)
    k2 = preview_cache.cache_key_for("id-1", "knowledgeBase/a.pptx", 100)
    k3 = preview_cache.cache_key_for("id-1", "knowledgeBase/a.pptx", 200)
    assert k1 == k2 and k1 != k3


class _Writer:
    """假的源文件写入回调，记下被调用了几次。"""

    def __init__(self, data: bytes | None) -> None:
        self.data = data
        self.calls: list[Path] = []

    async def __call__(self, target: Path) -> bool:
        self.calls.append(target)
        if self.data is None:
            return False
        await asyncio.to_thread(target.write_bytes, self.data)
        return True


def _fake_soffice(pdf: bytes | None, delay: float = 0) -> AsyncMock:
    async def run(_binary: str, input_path: Path, out_dir: Path, *_rest: Any) -> Path | None:
        await asyncio.sleep(delay)
        if pdf is None:
            return None
        out = out_dir / f"{input_path.stem}.pdf"
        await asyncio.to_thread(out.write_bytes, pdf)
        return out

    return AsyncMock(side_effect=run)


def _convert(writer: _Writer, cache_dir: str, key: str) -> Any:
    return office_preview.convert_office_to_pdf(
        writer, "PPTX", cache_dir=cache_dir, cache_key=key, max_cache_bytes=10**9
    )


async def test_convert_office_to_pdf_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = str(tmp_path / "cache")

    # 1. 未安装 LibreOffice 时平滑返回 None，也不去读源文件
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: None)
    writer = _Writer(b"pptx")
    assert await _convert(writer, cache_dir, "k1") is None
    assert writer.calls == []

    # 2. 转换成功落进磁盘缓存，第二次直接命中缓存，不再读源文件、不再起子进程
    run_mock = _fake_soffice(b"%PDF-1.4 converted")
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_preview, "_run_soffice", run_mock)
    path1 = await _convert(writer, cache_dir, "k2")
    assert path1 is not None and await asyncio.to_thread(path1.read_bytes) == b"%PDF-1.4 converted"
    assert await _convert(writer, cache_dir, "k2") == path1
    assert run_mock.await_count == 1 and len(writer.calls) == 1

    # 3. 源文件不存在：返回 None，不算转换失败，下次照常再试
    assert await _convert(_Writer(None), cache_dir, "k4") is None
    assert await preview_cache.failed_recently(cache_dir, "k4") is False

    # 4. 转换失败记失败标记，失败期内再打开不读源文件、不占名额重转
    failing = _fake_soffice(None)
    monkeypatch.setattr(office_preview, "_run_soffice", failing)
    retry_writer = _Writer(b"x")
    assert await _convert(retry_writer, cache_dir, "k3") is None
    assert await _convert(retry_writer, cache_dir, "k3") is None
    assert failing.await_count == 1 and len(retry_writer.calls) == 1
    assert await preview_cache.lookup(cache_dir, "k3") is None


async def test_same_file_converts_once_even_when_waiters_queue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """排队的请求在前一个人放锁、自己还没拿到锁时，新来的人不能另起一把锁并行重转。"""

    cache_dir = str(tmp_path / "cache")
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    failing = _fake_soffice(None, delay=0.02)
    monkeypatch.setattr(office_preview, "_run_soffice", failing)

    first = asyncio.create_task(_convert(_Writer(b"x"), cache_dir, "same"))
    await asyncio.sleep(0.005)
    waiter = asyncio.create_task(_convert(_Writer(b"x"), cache_dir, "same"))
    await asyncio.sleep(0.03)  # 第一个已转失败放锁，排队的还没跑到
    late = asyncio.create_task(_convert(_Writer(b"x"), cache_dir, "same"))
    assert await asyncio.gather(first, waiter, late) == [None, None, None]
    assert failing.await_count == 1
    assert len(office_preview._KEY_LOCKS) == 0  # 用完的锁都清掉，不越攒越多


async def test_key_locks_serialize_and_clean_up() -> None:
    locks = office_preview._KeyLocks()
    active = 0
    peak = 0

    async def use() -> None:
        nonlocal active, peak
        async with locks.hold("k"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    tasks = [asyncio.create_task(use())]
    await asyncio.sleep(0.005)
    tasks.append(asyncio.create_task(use()))
    await asyncio.sleep(0.008)  # 第一个刚放锁
    tasks.append(asyncio.create_task(use()))
    await asyncio.gather(*tasks)
    assert peak == 1
    assert len(locks) == 0


class _Proc:
    pid = 4321

    def __init__(self, returncode: int, on_communicate: Any) -> None:
        self.returncode = returncode
        self._on_communicate = on_communicate
        self.waited = False

    async def communicate(self) -> tuple[bytes, bytes]:
        result: tuple[bytes, bytes] = await self._on_communicate()
        return result

    async def wait(self) -> int:
        self.waited = True
        return self.returncode


async def test_run_soffice_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "source.pptx"
    src.write_bytes(b"pptx")
    profile = tmp_path / "profile"
    killed: list[int] = []
    monkeypatch.setattr(office_preview.sys, "platform", "linux")
    monkeypatch.setattr(office_preview.os, "killpg", lambda pid, sig: killed.append(pid), raising=False)
    monkeypatch.setattr(office_preview.signal, "SIGKILL", 9, raising=False)  # Windows 上跑单测时没有这个常量
    monkeypatch.setenv("THINKTANK_MINIO_SECRET_KEY", "secret")

    async def ok() -> tuple[bytes, bytes]:
        (tmp_path / "source.pdf").write_bytes(b"%PDF-ok")
        return b"", b""

    proc = _Proc(0, ok)
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", spawn)
    result = await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 10.0)
    assert result == tmp_path / "source.pdf"
    assert spawn.await_args is not None
    kwargs = spawn.await_args.kwargs
    assert kwargs["start_new_session"] is True
    assert "THINKTANK_MINIO_SECRET_KEY" not in kwargs["env"]
    assert killed == [4321] and proc.waited  # 正常退出也清掉同组残留的 soffice.bin
    # 每次转换的独立配置：宏不跑，Writer / Calc 打开文档时不更新外部链接
    xcu = await asyncio.to_thread((profile / "user" / "registrymodifications.xcu").read_text, encoding="utf-8")
    assert '"DisableMacrosExecution" oor:op="fuse"><value>true' in xcu
    assert 'Office.Writer/Content/Update">\n' not in xcu  # 续行符把 item 和 prop 拼在一行
    assert 'Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>0<' in xcu
    assert 'Office.Calc/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>1<' in xcu

    async def fail() -> tuple[bytes, bytes]:
        return b"", b"convert error"

    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=_Proc(1, fail)))
    assert await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 10.0) is None

    running = asyncio.Event()

    async def hang() -> tuple[bytes, bytes]:
        running.set()
        await asyncio.sleep(10)
        return b"", b""

    # 超时、请求被取消都整组杀掉并等它退出，不留孤儿和僵尸
    killed.clear()
    tproc = _Proc(-9, hang)
    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=tproc))
    assert await office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 0.05) is None
    assert killed == [4321] and tproc.waited

    killed.clear()
    running.clear()
    cproc = _Proc(-9, hang)
    monkeypatch.setattr(office_preview.asyncio, "create_subprocess_exec", AsyncMock(return_value=cproc))
    task = asyncio.create_task(office_preview._run_soffice("/usr/bin/soffice", src, tmp_path, profile, 10.0))
    await asyncio.wait_for(running.wait(), timeout=5)  # 子进程已经在跑，再取消请求
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert killed == [4321] and cproc.waited


def _opened_stream(*_args: Any, **_kwargs: Any) -> tuple[Any, int]:
    async def chunks() -> Any:
        yield b"pptx-"
        yield b"raw"

    return chunks(), 8


async def test_stream_office_preview_cache_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    row = _pptx_row()
    settings = SimpleNamespace(storage_dir=str(tmp_path), preview_cache_max_bytes=10**9)
    monkeypatch.setattr(knowledge, "get_settings", lambda: settings)
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge.repo, "is_favorited", AsyncMock(return_value=False))
    monkeypatch.setattr(knowledge.repo, "add_op_log", AsyncMock())
    monkeypatch.setattr(knowledge, "enqueue_event", AsyncMock())
    monkeypatch.setattr(office_preview, "has_libreoffice", lambda: True)

    # 1. preview_knowledge 返回 mode="pdf"
    session: Any = _Session()
    preview_res = await knowledge.preview_knowledge(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id)
    assert preview_res["preview"]["mode"] == "pdf"

    # 2. 缓存未命中 -> 按块拉源文件 -> 转 PDF -> 返回 application/pdf；转码前先交还数据库连接
    stream_mock = AsyncMock(side_effect=_opened_stream)
    monkeypatch.setattr(storage, "stream_object", stream_mock)
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    seen_input: list[bytes] = []

    async def run(_binary: str, input_path: Path, out_dir: Path, *_rest: Any) -> Path:
        seen_input.append(await asyncio.to_thread(input_path.read_bytes))
        out = out_dir / "source.pdf"
        await asyncio.to_thread(out.write_bytes, b"%PDF-1.4 pptx")
        return out

    monkeypatch.setattr(office_preview, "_run_soffice", AsyncMock(side_effect=run))
    session.commit.reset_mock()
    res = await knowledge.read_file_content(
        session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, for_download=False
    )
    assert res.media_type == "application/pdf"
    assert res.filename.endswith(".pdf")
    assert res.content == b"%PDF-1.4 pptx"
    assert seen_input == [b"pptx-raw"]
    assert stream_mock.await_count == 1
    assert session.commit.await_count == 1

    # 3. 二次预览直接命中磁盘缓存，不再访问对象存储
    res2 = await knowledge.read_file_content(
        session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, for_download=False
    )
    assert res2.content == b"%PDF-1.4 pptx"
    assert stream_mock.await_count == 1

    # 4. 对象存储连不上（真实的 stream_object 在没有本地副本时抛错）返回 503，而不是悄悄回摘要
    row2 = _pptx_row()
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row2))
    monkeypatch.setattr(storage, "stream_object", AsyncMock(side_effect=storage.StorageUnavailableError("down")))
    with pytest.raises(ApiError) as exc_info:
        await knowledge.read_file_content(session, actor=ACTOR, access=FULL_ACCESS, file_id=row2.id, for_download=False)
    assert exc_info.value.http_status == 503

    # 5. 源文件不存在时回摘要 txt
    monkeypatch.setattr(storage, "stream_object", AsyncMock(return_value=None))
    res3 = await knowledge.read_file_content(
        session, actor=ACTOR, access=FULL_ACCESS, file_id=row2.id, for_download=False
    )
    assert res3.media_type.startswith("text/plain")
