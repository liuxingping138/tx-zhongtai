"""预览用 PDF 的磁盘缓存（Office 转出的、PDF 瘦身线性化后的）：原子写入、按最近使用淘汰、失败标记、删文件时清掉。

缓存文件名是 `{key}.pdf`，key 由文件 ID + 对象键 + 大小（+ 形态）算出（`cache_key_for`），不含用户输入，
不会拼出目录穿越。
命中时更新修改时间，超过容量上限时从最久没用的删起（LRU）。转换失败记 `{key}.fail`，一段时间内不再重转，
免得一个总超时的文件每打开一次就占一个转换名额一分钟。
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import os
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

CHUNK_SIZE = 65536
FAIL_TTL_SECONDS = 600
# 中途被杀留下的临时文件，超过这个时间就当残留清掉（正常写一份 PDF 用不了这么久）。
_STALE_TMP_SECONDS = 3600


def cache_key_for(file_id: str, storage_path: str, size_bytes: int, variant: str = "") -> str:
    """`variant` 区分同一文件的不同预览形态；处理方式变了换一个，旧缓存不再命中，按容量上限慢慢淘汰。"""

    raw = f"{file_id}:{storage_path}:{size_bytes}" + (f":{variant}" if variant else "")
    return hashlib.sha256(raw.encode()).hexdigest()


class KeyLocks:
    """同一个文件同时只处理一次。记着每把锁有几个人在用，最后一个人走了才删，
    不会在前一个人刚放锁、排队的人还没拿到时就删掉，让后来的人另起一把锁并行重做。"""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @contextlib.asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock, users = self._locks[key]
            if users <= 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)

    def __len__(self) -> int:
        return len(self._locks)


def pdf_path(cache_dir: str, key: str) -> Path:
    return Path(cache_dir) / f"{key}.pdf"


def _fail_path(cache_dir: str, key: str) -> Path:
    return Path(cache_dir) / f"{key}.fail"


def _hit(path: Path) -> Path | None:
    try:
        os.utime(path)  # 记下最近一次使用，淘汰时按它排
    except FileNotFoundError:
        return None
    return path.resolve()


async def lookup(cache_dir: str, key: str) -> Path | None:
    """命中返回 PDF 路径（并记一次使用），没有返回 None。"""

    return await asyncio.to_thread(_hit, pdf_path(cache_dir, key))


def _failed_recently(path: Path, now: float) -> bool:
    try:
        return now - path.stat().st_mtime < FAIL_TTL_SECONDS
    except FileNotFoundError:
        return False


async def failed_recently(cache_dir: str, key: str) -> bool:
    return await asyncio.to_thread(_failed_recently, _fail_path(cache_dir, key), time.time())


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


async def mark_failed(cache_dir: str, key: str) -> None:
    await asyncio.to_thread(_touch, _fail_path(cache_dir, key))


def _install(source: Path, target: Path) -> None:
    """先复制成缓存目录里的唯一临时文件、落盘后再改名：读的人只会看到完整文件，并发写也不会互相截断。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.stem}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            shutil.copyfileobj(src, dst, CHUNK_SIZE)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
    with contextlib.suppress(FileNotFoundError):
        _fail_path(str(target.parent), target.stem).unlink()


def _stat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except FileNotFoundError:
        return None


def _drop_expired(cache_dir: Path, now: float) -> None:
    for pattern, ttl in (("*.fail", FAIL_TTL_SECONDS), (".*.tmp", _STALE_TMP_SECONDS)):
        for path in cache_dir.glob(pattern):
            st = _stat_or_none(path)
            if st is not None and now - st.st_mtime >= ttl:
                path.unlink(missing_ok=True)


def prune(cache_dir: str, max_bytes: int, *, keep: Path | None = None, now: float | None = None) -> int:
    """删掉过期的失败标记和残留临时文件；PDF 总量超过上限时从最久没用的删起（`keep` 是刚写好的，不删）。

    返回删掉的 PDF 个数。正在下发的文件已经打开，删掉目录项不影响它读完。
    """

    root = Path(cache_dir)
    if not root.is_dir():
        return 0
    _drop_expired(root, time.time() if now is None else now)
    entries = [(path, st) for path in root.glob("*.pdf") if (st := _stat_or_none(path)) is not None]
    total = sum(st.st_size for _path, st in entries)
    removed = 0
    for path, st in sorted(entries, key=lambda item: item[1].st_mtime):
        if total <= max_bytes:
            break
        if keep is not None and path.name == keep.name:
            continue
        path.unlink(missing_ok=True)
        total -= st.st_size
        removed += 1
    return removed


async def store(source: Path, cache_dir: str, key: str, *, max_bytes: int) -> Path:
    """把转好的 PDF 放进缓存并按容量上限淘汰，返回缓存路径。"""

    target = pdf_path(cache_dir, key)
    await asyncio.to_thread(_install, source, target)
    await asyncio.to_thread(functools.partial(prune, cache_dir, max_bytes, keep=target))
    return target.resolve()


def remove(cache_dir: str, key: str) -> None:
    """删文件时把它的预览缓存和失败标记一起删掉，删掉的资料不再留在磁盘上。"""

    pdf_path(cache_dir, key).unlink(missing_ok=True)
    _fail_path(cache_dir, key).unlink(missing_ok=True)


class FileChunks:
    """已打开的缓存文件按块读出；没开始读客户端就断开时，路由的后台任务调 aclose 关掉文件句柄。

    `select_range` 之后只读那一段（HTTP Range），不把整份文件读出来。
    """

    def __init__(self, fp: BinaryIO) -> None:
        self._fp = fp
        self._remaining: int | None = None

    def select_range(self, start: int, length: int) -> None:
        self._fp.seek(start)
        self._remaining = length

    def __aiter__(self) -> FileChunks:
        return self

    async def __anext__(self) -> bytes:
        size = CHUNK_SIZE if self._remaining is None else min(CHUNK_SIZE, self._remaining)
        chunk = await asyncio.to_thread(self._fp.read, size) if size > 0 else b""
        if not chunk:
            self._fp.close()
            raise StopAsyncIteration
        if self._remaining is not None:
            self._remaining -= len(chunk)
        return chunk

    async def aclose(self) -> None:
        self._fp.close()


def open_pdf(path: Path) -> tuple[FileChunks, int] | None:
    """在开始下发前就打开文件：之后被淘汰删掉目录项也能读完；已经被删了返回 None。"""

    try:
        fp = path.open("rb")
    except FileNotFoundError:
        return None
    return FileChunks(fp), os.fstat(fp.fileno()).st_size
