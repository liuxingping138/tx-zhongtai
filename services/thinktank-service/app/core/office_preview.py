"""Office 文档（PPT/Word/Excel）在线转 PDF 预览及磁盘缓存。"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from platform_common.logging_setup import get_logger

from app.core import storage

logger = get_logger(__name__)

OFFICE_EXTENSIONS: frozenset[str] = frozenset({"PPT", "PPTX", "DOC", "DOCX", "XLS", "XLSX"})
_FALLBACK_EXT_BY_SUFFIX: dict[str, str] = {"PPT": "PPTX", "WORD": "DOCX", "EXCEL": "XLSX"}
_CONVERT_SEMAPHORE = asyncio.Semaphore(2)
_INFLIGHT_LOCKS: dict[str, asyncio.Lock] = {}


def office_extension(filename: str, suffix: str) -> str | None:
    """识别可转为 PDF 预览的 Office 扩展名；非 Office 文档返回 None。"""

    raw_ext = storage.raw_extension(filename)
    if raw_ext in OFFICE_EXTENSIONS:
        return raw_ext
    upper_suffix = (suffix or "").upper()
    if upper_suffix in OFFICE_EXTENSIONS:
        return upper_suffix
    return _FALLBACK_EXT_BY_SUFFIX.get(upper_suffix)


def _soffice_binary() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def has_libreoffice() -> bool:
    return _soffice_binary() is not None


def cache_key_for(file_id: str, storage_path: str, size_bytes: int) -> str:
    return hashlib.sha256(f"{file_id}:{storage_path}:{size_bytes}".encode()).hexdigest()


def _read_cache(cache_path: Path) -> bytes | None:
    if cache_path.is_file():
        return cache_path.read_bytes()
    return None


async def read_cached_pdf(cache_dir: str, cache_key: str) -> bytes | None:
    """命中磁盘缓存时直接返回 PDF 字节，免去重复拉取 MinIO 和转码。"""

    return await asyncio.to_thread(_read_cache, Path(cache_dir) / f"{cache_key}.pdf")


def _write_cache_atomic(cache_path: Path, data: bytes) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".pdf.tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, cache_path)


async def _run_soffice(
    binary: str, input_path: Path, out_dir: Path, profile_dir: Path, timeout_seconds: float
) -> bytes | None:
    proc = await asyncio.create_subprocess_exec(
        binary,
        "--headless",
        "--nologo",
        "--nodefault",
        "--norestore",
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(input_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("office_preview_timeout", input=input_path.name, timeout_seconds=timeout_seconds)
        return None
    if proc.returncode != 0:
        logger.warning(
            "office_preview_failed", returncode=proc.returncode, stderr=stderr.decode("utf-8", "ignore")[:400]
        )
        return None
    pdf_path = out_dir / f"{input_path.stem}.pdf"
    if not pdf_path.is_file():
        return None
    return await asyncio.to_thread(pdf_path.read_bytes)


async def convert_office_to_pdf(
    raw: bytes,
    ext: str,
    *,
    cache_dir: str,
    cache_key: str,
    timeout_seconds: float = 60.0,
) -> bytes | None:
    """将 Office 字节流转为 PDF 并缓存到磁盘；转换失败或未安装 LibreOffice 时返回 None。"""

    cache_path = Path(cache_dir) / f"{cache_key}.pdf"
    cached = await asyncio.to_thread(_read_cache, cache_path)
    if cached is not None:
        return cached

    binary = _soffice_binary()
    if binary is None:
        return None

    key_lock = _INFLIGHT_LOCKS.setdefault(cache_key, asyncio.Lock())
    try:
        async with key_lock:
            cached = await asyncio.to_thread(_read_cache, cache_path)
            if cached is not None:
                return cached
            async with _CONVERT_SEMAPHORE:
                with tempfile.TemporaryDirectory(prefix="tt-office-") as tmp:
                    tmp_root = Path(tmp)
                    input_path = tmp_root / f"source.{ext.lower()}"
                    profile_dir = tmp_root / "profile"
                    await asyncio.to_thread(input_path.write_bytes, raw)
                    pdf_bytes = await _run_soffice(binary, input_path, tmp_root, profile_dir, timeout_seconds)
                    if pdf_bytes is None:
                        return None
                    await asyncio.to_thread(_write_cache_atomic, cache_path, pdf_bytes)
                    return pdf_bytes
    finally:
        if not key_lock.locked():
            _INFLIGHT_LOCKS.pop(cache_key, None)
