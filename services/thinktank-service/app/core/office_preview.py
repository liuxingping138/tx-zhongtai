"""Office 文档（PPT/Word/Excel）在线转 PDF 预览。缓存的读写、淘汰在 `preview_cache`。

内存只占固定大小：源文件边读边写进临时文件（拿到转换名额之后才读），转好的 PDF 留在缓存目录，按块流式下发。
LibreOffice 的 soffice 是壳脚本，真正干活的 soffice.bin 是孙进程，所以单开进程组，超时、请求取消都整组杀掉。
上传的文档不可信：转换进程只拿最少的环境变量，配置里关掉宏和外部链接更新，
免得文档把容器里的文件或内网地址的内容带进 PDF。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from platform_common.logging_setup import get_logger

from app.core import preview_cache, storage

logger = get_logger(__name__)

OFFICE_EXTENSIONS: frozenset[str] = frozenset({"PPT", "PPTX", "DOC", "DOCX", "XLS", "XLSX"})
# 文件名没有扩展名时按「文件格式」列猜：PPT 本身就在上面，WORD / EXCEL 是旧系统的写法。
# LibreOffice 按内容识别格式，扩展名只是提示，猜成新格式也能打开旧格式的文件。
_FALLBACK_EXT_BY_SUFFIX: dict[str, str] = {"WORD": "DOCX", "EXCEL": "XLSX"}
_CONVERT_SEMAPHORE = asyncio.Semaphore(2)
# 转换子进程只拿这几个环境变量：不把数据库口令、对象存储密钥、内部调用密钥交给处理上传文档的进程。
_CHILD_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "TZ")
# 每次转换的独立配置：宏一律不跑；Writer（0=从不）、Calc（1=从不）打开文档时不更新外部链接；不信任文档里的外部引用。
_PROFILE_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update">\
<prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Content/Update">\
<prop oor:name="Link" oor:op="fuse"><value>1</value></prop></item>
</oor:items>
"""

# 写源文件的回调：把源文件写到给定路径，源文件不存在返回 False。
SourceWriter = Callable[[Path], Awaitable[bool]]


class _KeyLocks:
    """同一个文件同时只转一次。记着每把锁有几个人在用，最后一个人走了才删，
    不会在前一个人刚放锁、排队的人还没拿到时就删掉，让后来的人另起一把锁并行重转。"""

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


_KEY_LOCKS = _KeyLocks()


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


def _child_env(home: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in _CHILD_ENV_KEYS if key in os.environ}
    env["HOME"] = str(home)
    return env


def _write_profile(profile_dir: Path) -> None:
    user_dir = profile_dir / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "registrymodifications.xcu").write_text(_PROFILE_XCU, encoding="utf-8")


async def _kill_group(proc: asyncio.subprocess.Process) -> None:
    # 壳进程退出了，同组的 soffice.bin 也可能还在，所以不看 returncode，整组都发；组里没人了就是 ProcessLookupError。
    if sys.platform != "win32":  # 只在 Linux 容器里跑；Windows 上跑单测时没有进程组
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    # 不等它退出就会留下僵尸；被取消时也要等完，所以屏蔽取消。
    await asyncio.shield(proc.wait())


async def _run_soffice(
    binary: str, input_path: Path, out_dir: Path, profile_dir: Path, timeout_seconds: float
) -> Path | None:
    await asyncio.to_thread(_write_profile, profile_dir)
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
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=_child_env(profile_dir.parent),
        start_new_session=True,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("office_preview_timeout", input=input_path.name, timeout_seconds=timeout_seconds)
        return None
    finally:
        # 正常退出后 soffice.bin 也可能还挂着；超时、请求取消时整组杀掉。
        await _kill_group(proc)
    if proc.returncode != 0:
        logger.warning(
            "office_preview_failed", returncode=proc.returncode, stderr=(stderr or b"").decode("utf-8", "ignore")[:400]
        )
        return None
    pdf_path = out_dir / f"{input_path.stem}.pdf"
    return pdf_path if pdf_path.is_file() else None


@dataclass(frozen=True)
class _CacheSlot:
    """这次转换的结果放进缓存的哪里、缓存总量上限多少。"""

    cache_dir: str
    cache_key: str
    max_bytes: int


async def _convert_once(
    binary: str, write_source: SourceWriter, ext: str, slot: _CacheSlot, limit_seconds: float
) -> Path | None:
    with tempfile.TemporaryDirectory(prefix="tt-office-") as tmp:
        tmp_root = Path(tmp)
        input_path = tmp_root / f"source.{ext.lower()}"
        out_dir = tmp_root / "out"
        out_dir.mkdir()
        if not await write_source(input_path):
            return None  # 源文件不存在不算转换失败，不记失败标记
        pdf_path = await _run_soffice(binary, input_path, out_dir, tmp_root / "profile", limit_seconds)
        if pdf_path is None:
            await preview_cache.mark_failed(slot.cache_dir, slot.cache_key)
            return None
        return await preview_cache.store(pdf_path, slot.cache_dir, slot.cache_key, max_bytes=slot.max_bytes)


async def convert_office_to_pdf(
    write_source: SourceWriter,
    ext: str,
    *,
    cache_dir: str,
    cache_key: str,
    max_cache_bytes: int,
    timeout_seconds: float = 60.0,
) -> Path | None:
    """转出 PDF 并缓存到磁盘，返回缓存文件路径；源文件不存在、转换失败或未安装 LibreOffice 时返回 None。

    源文件在拿到转换名额之后才读，排队的请求不占内存。最近转失败过的直接返回 None，不再占名额重转。
    """

    cached = await preview_cache.lookup(cache_dir, cache_key)
    if cached is not None:
        return cached
    binary = _soffice_binary()
    if binary is None or await preview_cache.failed_recently(cache_dir, cache_key):
        return None
    async with _KEY_LOCKS.hold(cache_key):
        cached = await preview_cache.lookup(cache_dir, cache_key)
        if cached is not None:
            return cached
        if await preview_cache.failed_recently(cache_dir, cache_key):
            return None  # 排队时前一个人刚转失败
        async with _CONVERT_SEMAPHORE:
            slot = _CacheSlot(cache_dir, cache_key, max_cache_bytes)
            return await _convert_once(binary, write_source, ext, slot, timeout_seconds)
