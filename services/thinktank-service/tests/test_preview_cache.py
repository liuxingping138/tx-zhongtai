"""Office 预览 PDF 磁盘缓存：原子写入、LRU 淘汰、失败标记、删文件清理、提前打开的文件流。"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from app.core import preview_cache


def _write(path: Path, size: int, mtime: float) -> None:
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_prune_evicts_least_recently_used_and_keeps_new_file(tmp_path: Path) -> None:
    now = time.time()
    _write(tmp_path / "old.pdf", 400, now - 300)
    _write(tmp_path / "mid.pdf", 400, now - 200)
    _write(tmp_path / "new.pdf", 400, now - 100)

    assert preview_cache.prune(str(tmp_path), 800, now=now) == 1
    assert sorted(p.name for p in tmp_path.glob("*.pdf")) == ["mid.pdf", "new.pdf"]

    # 刚写好的那份即使最旧、即使自己就超过上限也不删，否则这次请求拿不到它
    assert preview_cache.prune(str(tmp_path), 100, keep=tmp_path / "mid.pdf", now=now) == 1
    assert [p.name for p in tmp_path.glob("*.pdf")] == ["mid.pdf"]
    assert preview_cache.prune(str(tmp_path / "missing"), 0) == 0


def test_prune_drops_expired_markers_and_stale_tmp(tmp_path: Path) -> None:
    now = time.time()
    _write(tmp_path / "a.fail", 0, now - preview_cache.FAIL_TTL_SECONDS - 1)
    _write(tmp_path / "b.fail", 0, now - 10)
    _write(tmp_path / ".c-123.tmp", 10, now - 7200)
    _write(tmp_path / ".d-456.tmp", 10, now - 10)

    preview_cache.prune(str(tmp_path), 10**9, now=now)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".d-456.tmp", "b.fail"]


async def test_store_lookup_failure_marker_and_remove(tmp_path: Path) -> None:
    cache_dir = str(tmp_path / "cache")
    src = tmp_path / "out.pdf"
    await asyncio.to_thread(src.write_bytes, b"%PDF-1")

    assert await preview_cache.lookup(cache_dir, "k") is None
    assert await preview_cache.failed_recently(cache_dir, "k") is False
    await preview_cache.mark_failed(cache_dir, "k")
    assert await preview_cache.failed_recently(cache_dir, "k") is True

    stored = await preview_cache.store(src, cache_dir, "k", max_bytes=10**9)
    assert await asyncio.to_thread(stored.read_bytes) == b"%PDF-1"
    # 转成功后失败标记作废，也不留临时文件
    assert await preview_cache.failed_recently(cache_dir, "k") is False
    assert not await asyncio.to_thread(lambda: list(Path(cache_dir).glob(".*.tmp")))

    # 命中会刷新修改时间，淘汰按最近使用排
    await asyncio.to_thread(os.utime, stored, (1, 1))
    assert await preview_cache.lookup(cache_dir, "k") == stored
    assert (await asyncio.to_thread(stored.stat)).st_mtime > 1

    await preview_cache.mark_failed(cache_dir, "k")
    await asyncio.to_thread(preview_cache.remove, cache_dir, "k")
    assert await preview_cache.lookup(cache_dir, "k") is None
    assert await preview_cache.failed_recently(cache_dir, "k") is False
    await asyncio.to_thread(preview_cache.remove, cache_dir, "k")  # 再删一次不报错


async def test_open_pdf_reads_after_unlink_and_closes(tmp_path: Path) -> None:
    path = tmp_path / "k.pdf"
    await asyncio.to_thread(path.write_bytes, b"a" * (preview_cache.CHUNK_SIZE + 5))
    assert preview_cache.open_pdf(tmp_path / "missing.pdf") is None

    opened = preview_cache.open_pdf(path)
    assert opened is not None
    stream, size = opened
    assert size == preview_cache.CHUNK_SIZE + 5
    if os.name != "nt":  # Windows 不允许删除已打开的文件；容器里是 Linux
        await asyncio.to_thread(path.unlink)  # 被淘汰删掉目录项也能读完
    chunks = [chunk async for chunk in stream]
    assert [len(c) for c in chunks] == [preview_cache.CHUNK_SIZE, 5]

    other = tmp_path / "other.pdf"
    await asyncio.to_thread(other.write_bytes, b"%PDF")
    unread = preview_cache.open_pdf(other)
    assert unread is not None
    await unread[0].aclose()  # 没开始读客户端就断开：路由的后台任务关掉句柄
    await asyncio.to_thread(other.unlink)  # 句柄关了，Windows 上也删得掉
