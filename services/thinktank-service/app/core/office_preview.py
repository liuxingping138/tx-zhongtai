"""Office 文档（PPT/Word/Excel）在线转 PDF 预览。缓存的读写、淘汰在 `preview_cache`。

转出来的 PDF 再经 `pdf_optimize` 压缩、线性化后才进缓存，前端按 Range 先取第一页。

内存只占固定大小：源文件边读边写进临时文件（拿到转换名额之后才读），转好的 PDF 留在缓存目录，按块流式下发。
LibreOffice 的 soffice 是壳脚本，真正干活的 soffice.bin 是孙进程，所以单开进程组，超时、请求取消都整组杀掉。
上传的文档不可信：转换进程只拿最少的环境变量，配置里关掉宏和外部链接更新，
免得文档把容器里的文件或内网地址的内容带进 PDF。
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from platform_common.logging_setup import get_logger

from app.core import pdf_optimize, preview_cache, preview_slots, storage, subprocess_guard

logger = get_logger(__name__)

OFFICE_EXTENSIONS: frozenset[str] = frozenset({"PPT", "PPTX", "DOC", "DOCX", "XLS", "XLSX"})
# 文件名没有扩展名时按「文件格式」列猜：PPT 本身就在上面，WORD / EXCEL 是旧系统的写法。
# LibreOffice 按内容识别格式，扩展名只是提示，猜成新格式也能打开旧格式的文件。
_FALLBACK_EXT_BY_SUFFIX: dict[str, str] = {"WORD": "DOCX", "EXCEL": "XLSX"}
_CONVERT_TIMEOUT_SECONDS = 60.0
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
SourceWriter = pdf_optimize.SourceWriter

# 同一个文件同时只转一次。
_KEY_LOCKS = preview_cache.KeyLocks()


def office_extension(filename: str, suffix: str, storage_path: str = "") -> str | None:
    """识别可转为 PDF 预览的 Office 扩展名；非 Office 文档返回 None。"""

    ext = storage.effective_extension(filename, suffix, storage_path)
    if ext in OFFICE_EXTENSIONS:
        return ext
    return _FALLBACK_EXT_BY_SUFFIX.get(ext)


def _soffice_binary() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def has_libreoffice() -> bool:
    return _soffice_binary() is not None


def _write_profile(profile_dir: Path) -> None:
    user_dir = profile_dir / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "registrymodifications.xcu").write_text(_PROFILE_XCU, encoding="utf-8")


async def _run_soffice(
    binary: str, input_path: Path, out_dir: Path, profile_dir: Path, timeout_seconds: float
) -> Path | None:
    await asyncio.to_thread(_write_profile, profile_dir)
    # 正常退出后 soffice.bin 也可能还挂着；结束、超时、请求取消时都整组杀掉。
    code = await subprocess_guard.run_isolated(
        [
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
        ],
        home=profile_dir.parent,
        timeout_seconds=timeout_seconds,
        label="soffice",
    )
    if code != 0:
        return None
    pdf_path = out_dir / f"{input_path.stem}.pdf"
    return pdf_path if pdf_path.is_file() else None


@dataclass(frozen=True)
class _CacheSlot:
    """这次转换的结果放进缓存的哪里、缓存总量上限多少。"""

    cache_dir: str
    cache_key: str
    max_bytes: int
    optimize: pdf_optimize.OptimizeOptions | None = None


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
        try:
            if slot.optimize is not None:
                pdf_path = await pdf_optimize.optimize_file(pdf_path, tmp_root, slot.optimize, force_compress=True)
            return await preview_cache.store(pdf_path, slot.cache_dir, slot.cache_key, max_bytes=slot.max_bytes)
        except preview_cache.FileDeletedError:
            raise  # 转换途中文件被删：不是失败，不记失败标记
        except OSError as exc:
            # 写缓存失败（如磁盘满）、起不了 gs / qpdf：记失败标记，10 分钟内回摘要，不再每打开一次就占名额重转
            logger.warning("office_preview_cache_failed", error=str(exc))
            with contextlib.suppress(OSError):
                await preview_cache.mark_failed(slot.cache_dir, slot.cache_key)
            return None


async def convert_office_to_pdf(
    write_source: SourceWriter,
    ext: str,
    cache: pdf_optimize.CacheSlot,
    *,
    optimize: pdf_optimize.OptimizeOptions | None = None,
    wait: bool = True,
) -> Path | None:
    """转出 PDF 并缓存到磁盘，返回缓存文件路径；源文件不存在、转换失败或未安装 LibreOffice 时返回 None。

    给了 `optimize` 就把转出的 PDF 压缩、线性化后再缓存。
    源文件在拿到转换名额之后才读，排队的请求不占内存。最近转失败过的直接返回 None，不再占名额重转。
    名额和 PDF 压缩共用（`preview_slots`）；`wait=False` 时名额已满抛 `preview_slots.SlotBusyError`。
    """

    cache_dir, cache_key = cache.cache_dir, cache.cache_key

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
        async with preview_slots.hold(wait=wait):
            slot = _CacheSlot(cache_dir, cache_key, cache.max_bytes, optimize)
            return await _convert_once(binary, write_source, ext, slot, _CONVERT_TIMEOUT_SECONDS)
