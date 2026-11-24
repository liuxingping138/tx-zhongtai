"""预览转码的并发与收尾：删除途中的转换不留缓存、Office 写缓存失败记失败标记、
转码压缩合计名额、预热不排队、stderr 只留开头。
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import NotFoundError

from app.core import office_preview, pdf_optimize, preview_cache, preview_slots, subprocess_guard
from app.knowledge.application import knowledge_preview, preview_warmup
from app.knowledge.domain.models import KnowledgeFile
from tests.helpers import no_pdf_tools, preview_settings

PDF = b"%PDF-1.4 body"
OPTIONS = pdf_optimize.OptimizeOptions(compress_min_bytes=10**9, dpi=144, timeout_seconds=5.0)


async def _write(target: Path, data: bytes = PDF) -> bool:
    await asyncio.to_thread(target.write_bytes, data)
    return True


def _cache_files(cache_dir: Path, pattern: str) -> list[Path]:
    return sorted(cache_dir.glob(pattern)) if cache_dir.is_dir() else []


# ---- H1：删除时正在转换，转完不留缓存 ----


async def test_pdf_deleted_during_optimize_leaves_no_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(pdf_optimize, "_gs_binary", lambda: None)
    monkeypatch.setattr(pdf_optimize, "_qpdf_binary", lambda: "/usr/bin/qpdf")

    async def qpdf_then_deleted(args: list[str], **_kwargs: Any) -> int:
        await asyncio.to_thread(Path(args[-1]).write_bytes, b"LINEAR:" + PDF)
        # 线性化的这一会儿有人删了这个文件：删除只看得到还没写进缓存的空位
        await asyncio.to_thread(preview_cache.remove, str(cache_dir), "k")
        return 0

    monkeypatch.setattr(subprocess_guard, "run_isolated", qpdf_then_deleted)
    slot = pdf_optimize.CacheSlot(str(cache_dir), "k", 10**9)
    with pytest.raises(preview_cache.FileDeletedError):
        await pdf_optimize.prepare_pdf_preview(_write, slot, OPTIONS)
    assert _cache_files(cache_dir, "*.pdf") == []
    assert _cache_files(cache_dir, "*.fail") == []  # 被删不算转换失败
    assert _cache_files(cache_dir, ".*.tmp") == []


async def test_office_deleted_during_convert_leaves_no_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    no_pdf_tools(monkeypatch)
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")

    async def soffice(_binary: str, _input: Path, out_dir: Path, *_rest: Any) -> Path:
        out = out_dir / "source.pdf"
        await asyncio.to_thread(out.write_bytes, PDF)
        await asyncio.to_thread(preview_cache.remove, str(cache_dir), "o")
        return out

    monkeypatch.setattr(office_preview, "_run_soffice", soffice)
    with pytest.raises(preview_cache.FileDeletedError):
        await office_preview.convert_office_to_pdf(
            _write, "PPTX", pdf_optimize.CacheSlot(str(cache_dir), "o", 10**9), optimize=OPTIONS
        )
    assert _cache_files(cache_dir, "*.pdf") == []
    assert _cache_files(cache_dir, "*.fail") == []


def test_cache_written_before_delete_is_removed_and_tombstone_expires(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    source = tmp_path / "src.pdf"
    source.write_bytes(PDF)
    preview_cache._install(source, preview_cache.pdf_path(str(cache_dir), "k"))
    preview_cache.remove(str(cache_dir), "k")  # 先写好、后删除：删除这边删得掉
    assert _cache_files(cache_dir, "*.pdf") == []
    assert [p.name for p in _cache_files(cache_dir, "*.deleted")] == ["k.deleted"]
    preview_cache.prune(str(cache_dir), 10**9, now=time.time() + 2 * 86400)
    assert _cache_files(cache_dir, "*.deleted") == []  # 墓碑过期清掉，不越积越多


def _row() -> KnowledgeFile:
    return KnowledgeFile(
        id=uuid.uuid4(), file_name="方案.pdf", file_suffix="PDF", storage_path="k/a.pdf", file_size_bytes=8
    )


def _session_factory(row: KnowledgeFile | None, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(preview_warmup.repo, "get_by_id", AsyncMock(return_value=row))

    @asynccontextmanager
    async def _session() -> AsyncIterator[None]:
        yield None

    return _session


def _logs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []

    def record(event: str, **kw: Any) -> None:
        seen.append((event, kw))

    monkeypatch.setattr(preview_warmup, "logger", SimpleNamespace(info=record, warning=record))
    return seen


async def test_warmup_of_file_deleted_midway_logs_deleted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = preview_settings(tmp_path)
    monkeypatch.setattr(preview_warmup, "get_settings", lambda: settings)
    no_pdf_tools(monkeypatch)
    row = _row()

    async def opened(*_args: Any, **_kwargs: Any) -> tuple[AsyncIterator[bytes], int]:
        async def chunks() -> AsyncIterator[bytes]:
            await knowledge_preview.drop_preview_cache(settings, row)  # 拉源文件的途中被删
            yield PDF

        return chunks(), len(PDF)

    monkeypatch.setattr(knowledge_preview.storage, "stream_object", opened)
    logs = _logs(monkeypatch)
    await preview_warmup.warm_preview(row.id, session_factory=_session_factory(row, monkeypatch))
    assert logs == [("preview_warmup_skipped", {"file_id": str(row.id), "reason": "deleted"})]
    assert _cache_files(tmp_path / "preview_cache", "*.pdf") == []
    # 正在打开预览的人拿到 404，不是 500
    with pytest.raises(NotFoundError):
        await knowledge_preview.open_preview_pdf(settings, row, None)


# ---- M1：Office 写缓存失败记失败标记，不再每次重转 ----


async def test_office_cache_write_failure_marks_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    no_pdf_tools(monkeypatch)
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    runs: list[Path] = []

    async def soffice(_binary: str, _input: Path, out_dir: Path, *_rest: Any) -> Path:
        out = out_dir / "source.pdf"
        await asyncio.to_thread(out.write_bytes, PDF)
        runs.append(out)
        return out

    monkeypatch.setattr(office_preview, "_run_soffice", soffice)
    monkeypatch.setattr(preview_cache, "store", AsyncMock(side_effect=OSError(28, "No space left on device")))
    slot = pdf_optimize.CacheSlot(str(cache_dir), "o", 10**9)
    assert await office_preview.convert_office_to_pdf(_write, "DOCX", slot, optimize=OPTIONS) is None
    assert await preview_cache.failed_recently(str(cache_dir), "o")
    # 10 分钟内再打开：直接回摘要，不再占名额重转
    assert await office_preview.convert_office_to_pdf(_write, "DOCX", slot, optimize=OPTIONS) is None
    assert len(runs) == 1


# ---- M2：Office 转码和 PDF 压缩合计同时最多 MAX_JOBS 个重进程 ----


async def test_office_and_pdf_share_heavy_process_slots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    active = 0
    peak = 0
    gate = asyncio.Event()

    async def heavy() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await gate.wait()
        active -= 1

    async def soffice(_binary: str, _input: Path, out_dir: Path, *_rest: Any) -> Path:
        await heavy()
        out = out_dir / "source.pdf"
        await asyncio.to_thread(out.write_bytes, PDF)
        return out

    async def tool(args: list[str], **_kwargs: Any) -> int:
        await heavy()
        await asyncio.to_thread(Path(args[-1]).write_bytes, b"LINEAR:" + PDF)
        return 0

    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_preview, "_run_soffice", soffice)
    monkeypatch.setattr(pdf_optimize, "_gs_binary", lambda: None)
    monkeypatch.setattr(pdf_optimize, "_qpdf_binary", lambda: "/usr/bin/qpdf")
    monkeypatch.setattr(subprocess_guard, "run_isolated", tool)
    cache_dir = str(tmp_path / "cache")
    jobs = [
        *(
            office_preview.convert_office_to_pdf(
                _write, "PPTX", pdf_optimize.CacheSlot(cache_dir, f"o{i}", 10**9), optimize=OPTIONS
            )
            for i in range(3)
        ),
        *(
            pdf_optimize.prepare_pdf_preview(_write, pdf_optimize.CacheSlot(cache_dir, f"p{i}", 10**9), OPTIONS)
            for i in range(3)
        ),
    ]
    tasks = [asyncio.create_task(job) for job in jobs]
    await asyncio.sleep(0.1)
    assert peak == preview_slots.MAX_JOBS
    gate.set()
    results = await asyncio.gather(*tasks)
    assert all(path is not None for path in results)
    assert peak == preview_slots.MAX_JOBS  # 6 个任务（Office 每个还连着跑 qpdf）始终没超过合计名额


# ---- M3：预热在拿名额的那一刻名额已满就跳过，不排队 ----


async def test_hold_without_wait_raises_when_full_and_acquires_when_free() -> None:
    release = asyncio.Event()
    holding = asyncio.Event()
    entered = 0

    async def occupy() -> None:
        nonlocal entered
        async with preview_slots.hold():
            entered += 1
            if entered == preview_slots.MAX_JOBS:
                holding.set()
            await release.wait()

    tasks = [asyncio.create_task(occupy()) for _ in range(preview_slots.MAX_JOBS)]
    await asyncio.wait_for(holding.wait(), timeout=5)
    with pytest.raises(preview_slots.SlotBusyError):
        async with preview_slots.hold(wait=False):
            pytest.fail("名额满了不该拿到")
    release.set()
    await asyncio.gather(*tasks)
    async with preview_slots.hold(wait=False):
        assert not preview_slots.has_free_slot() or preview_slots.MAX_JOBS > 1


async def test_warmup_skips_when_slots_fill_between_check_and_acquire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = preview_settings(tmp_path)
    monkeypatch.setattr(preview_warmup, "get_settings", lambda: settings)
    # 预检查时还有空（读行、查缓存的这会儿名额被正在看的人拿走了）
    monkeypatch.setattr(preview_slots, "has_free_slot", lambda: True)
    fetched = AsyncMock(side_effect=AssertionError("名额满了不该去拉源文件"))
    monkeypatch.setattr(knowledge_preview.storage, "stream_object", fetched)
    row = _row()
    logs = _logs(monkeypatch)
    release = asyncio.Event()
    full = asyncio.Event()
    entered = 0

    async def viewer() -> None:
        nonlocal entered
        async with preview_slots.hold():
            entered += 1
            if entered == preview_slots.MAX_JOBS:
                full.set()
            await release.wait()

    viewers = [asyncio.create_task(viewer()) for _ in range(preview_slots.MAX_JOBS)]
    await asyncio.wait_for(full.wait(), timeout=5)
    try:
        await asyncio.wait_for(
            preview_warmup.warm_preview(row.id, session_factory=_session_factory(row, monkeypatch)), 5
        )
    finally:
        release.set()
        await asyncio.gather(*viewers)
    assert logs == [("preview_warmup_skipped", {"file_id": str(row.id), "reason": "busy"})]
    fetched.assert_not_awaited()


# ---- L5：stderr 读完但只留开头 ----


async def test_run_isolated_keeps_only_head_of_huge_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(subprocess_guard, "logger", SimpleNamespace(warning=lambda _event, **kw: seen.append(kw)))
    noisy = [sys.executable, "-c", "import sys; sys.stderr.write('E' * 2_000_000); sys.exit(1)"]
    assert await subprocess_guard.run_isolated(noisy, home=tmp_path, timeout_seconds=30, label="gs") == 1
    assert seen and seen[-1]["stderr"] == "E" * 400


async def test_drain_reads_to_eof_but_keeps_limit() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"a" * 100_000)
    reader.feed_data(b"b" * 100_000)
    reader.feed_eof()
    assert await subprocess_guard._drain(reader, 10) == b"a" * 10
    assert reader.at_eof()
    assert await subprocess_guard._drain(None, 10) == b""
