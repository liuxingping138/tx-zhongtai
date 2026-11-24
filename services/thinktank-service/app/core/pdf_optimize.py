"""预览用 PDF：轻量压缩（Ghostscript）+ 线性化（qpdf），结果放进预览缓存，按 Range 分段下发。

服务器出口只有 3～4 Mbps，一份 23MB 的扫描版 PDF 整份下完要将近一分钟。所以预览走另一份文件：
1. 超过 `compress_min_bytes` 的（以及 LibreOffice 转出来的）先用 gs 重写：文字、矢量不动，
   内嵌图片降到 `dpi`（默认 144，屏幕上看足够）。没变小（不到原来的 90%）就不用它。
2. 再用 `qpdf --linearize` 线性化（Fast Web View）：第一页和它需要的对象排到文件开头，
   前端 PDF.js 按 Range 取头几百 KB 就能画出第一页。
任何一步失败都退回上一步的结果，工具都没装也照样缓存原文件：之后的 Range 请求读本地盘，不再每次去对象存储拉整份。
下载（`/download`）不经过这里，永远给对象存储里的原文件。

和 Office 转换一样：同一个文件同时只做一次，和 Office 转换合计同时最多做 2 个（`preview_slots`），
子进程单开进程组、超时整组杀掉、只带最少的环境变量；
写缓存失败（如磁盘满）记失败标记，10 分钟内直接回退到从对象存储整份读，不再占名额重做。
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from platform_common.logging_setup import get_logger

from app.core import preview_cache, preview_slots, subprocess_guard

logger = get_logger(__name__)

# 压缩后至少要小到原来的这个比例才用，省得为了省几个百分点换掉原文件（gs 重写偶尔还会变大）。
MIN_SAVING_RATIO = 0.9
# qpdf 退出码：0 成功，3 有警告但输出可用（常见于小毛病的 PDF），其他为失败。
_QPDF_OK = frozenset({0, 3})
_KEY_LOCKS = preview_cache.KeyLocks()

# 写源文件的回调：把源文件写到给定路径，源文件不存在返回 False。
SourceWriter = Callable[[Path], Awaitable[bool]]


@dataclass(frozen=True)
class OptimizeOptions:
    compress_min_bytes: int
    dpi: int
    timeout_seconds: float


@dataclass(frozen=True)
class CacheSlot:
    """结果放进缓存的哪里、缓存总量上限多少。"""

    cache_dir: str
    cache_key: str
    max_bytes: int


def _gs_binary() -> str | None:
    return shutil.which("gs")


def _qpdf_binary() -> str | None:
    return shutil.which("qpdf")


def _gs_args(binary: str, source: Path, target: Path, dpi: int) -> list[str]:
    # 黑白（1 位）图多是扫描的文字，降得太狠会糊，给两倍分辨率。
    mono_dpi = dpi * 2
    return [
        binary,
        "-q",
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        "-dAutoRotatePages=/None",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dColorImageDownsampleThreshold=1.0",
        "-dGrayImageDownsampleThreshold=1.0",
        "-dMonoImageDownsampleThreshold=1.0",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={mono_dpi}",
        f"-sOutputFile={target}",
        str(source),
    ]


def _size(path: Path) -> int:
    """文件大小；不存在算 0。"""

    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


async def compress(source: Path, work_dir: Path, options: OptimizeOptions) -> Path | None:
    """gs 重写并降图片分辨率；没装、失败、超时或没明显变小都返回 None。"""

    binary = _gs_binary()
    if binary is None:
        return None
    target = work_dir / "compressed.pdf"
    code = await subprocess_guard.run_isolated(
        _gs_args(binary, source, target, options.dpi),
        home=work_dir,
        timeout_seconds=options.timeout_seconds,
        label="ghostscript",
    )
    after = await asyncio.to_thread(_size, target)
    if code != 0 or after == 0:
        return None
    before = await asyncio.to_thread(_size, source)
    if after > before * MIN_SAVING_RATIO:
        logger.info("pdf_compress_skipped", before=before, after=after)
        return None
    return target


async def linearize(source: Path, work_dir: Path, options: OptimizeOptions) -> Path | None:
    """qpdf 线性化；没装、失败或超时返回 None。"""

    binary = _qpdf_binary()
    if binary is None:
        return None
    target = work_dir / f"{source.stem}-linear.pdf"
    code = await subprocess_guard.run_isolated(
        [binary, "--linearize", str(source), str(target)],
        home=work_dir,
        timeout_seconds=options.timeout_seconds,
        label="qpdf",
    )
    if code not in _QPDF_OK or await asyncio.to_thread(_size, target) == 0:
        return None
    return target


async def optimize_file(source: Path, work_dir: Path, options: OptimizeOptions, *, force_compress: bool) -> Path:
    """返回给预览用的那一份：能压就压、能线性化就线性化，都不行就是 `source` 本身，不会失败。"""

    best = source
    if force_compress or await asyncio.to_thread(_size, source) >= options.compress_min_bytes:
        best = await compress(source, work_dir, options) or source
    return await linearize(best, work_dir, options) or best


async def _prepare_once(write_source: SourceWriter, slot: CacheSlot, options: OptimizeOptions) -> Path | None:
    with tempfile.TemporaryDirectory(prefix="tt-pdf-") as tmp:
        work_dir = Path(tmp)
        source = work_dir / "source.pdf"
        if not await write_source(source):
            return None  # 源文件不存在不算失败，不记失败标记
        try:
            best = await optimize_file(source, work_dir, options, force_compress=False)
            return await preview_cache.store(best, slot.cache_dir, slot.cache_key, max_bytes=slot.max_bytes)
        except preview_cache.FileDeletedError:
            raise  # 转换途中文件被删：不是失败，不记失败标记
        except OSError as exc:
            logger.warning("pdf_preview_cache_failed", error=str(exc))
            with contextlib.suppress(OSError):  # 磁盘满时连失败标记也可能写不进去，照样回退
                await preview_cache.mark_failed(slot.cache_dir, slot.cache_key)
            return None


async def prepare_pdf_preview(
    write_source: SourceWriter, slot: CacheSlot, options: OptimizeOptions, *, wait: bool = True
) -> Path | None:
    """返回缓存里给预览用的 PDF 路径；源文件不存在或最近写缓存失败过返回 None（调用方整份读原文件）。

    `wait=False`（上传后的预热）：要做的时候名额已满就抛 `preview_slots.SlotBusyError`，不排队。
    """

    cached = await preview_cache.lookup(slot.cache_dir, slot.cache_key)
    if cached is not None:
        return cached
    if await preview_cache.failed_recently(slot.cache_dir, slot.cache_key):
        return None
    async with _KEY_LOCKS.hold(slot.cache_key):
        cached = await preview_cache.lookup(slot.cache_dir, slot.cache_key)
        if cached is not None:
            return cached  # 排队时前一个人已经做好
        if await preview_cache.failed_recently(slot.cache_dir, slot.cache_key):
            return None
        async with preview_slots.hold(wait=wait):
            return await _prepare_once(write_source, slot, options)
