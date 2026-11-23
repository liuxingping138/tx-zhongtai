"""预览用 PDF 的压缩、线性化与缓存：每一步失败都退回上一步，最差也缓存原文件；同一文件只做一次。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core import office_preview, pdf_optimize, preview_cache, subprocess_guard

SMALL = b"%PDF-1.4 small"
LARGE = b"%PDF-1.4 " + b"x" * 2000
OPTIONS = pdf_optimize.OptimizeOptions(compress_min_bytes=1000, dpi=144, timeout_seconds=5.0)


class _Writer:
    def __init__(self, data: bytes | None) -> None:
        self.data = data
        self.calls = 0

    async def __call__(self, target: Path) -> bool:
        self.calls += 1
        if self.data is None:
            return False
        await asyncio.to_thread(target.write_bytes, self.data)
        return True


class _Tools:
    """假的 gs / qpdf：记下调用，按设定的退出码写输出。gs 输出取原文件前 `gs_keep` 个字节，qpdf 在前面加 LINEAR:。"""

    def __init__(self, *, gs_code: int | None = 0, qpdf_code: int | None = 0, gs_keep: int = 100) -> None:
        self.gs_code, self.qpdf_code, self.gs_keep = gs_code, qpdf_code, gs_keep
        self.calls: list[list[str]] = []

    def _write(self, args: list[str], label: str) -> int | None:
        if label == "ghostscript":
            if self.gs_code == 0:
                out = Path(next(a for a in args if a.startswith("-sOutputFile="))[len("-sOutputFile=") :])
                out.write_bytes(Path(args[-1]).read_bytes()[: self.gs_keep])
            return self.gs_code
        if self.qpdf_code in {0, 3}:
            Path(args[-1]).write_bytes(b"LINEAR:" + Path(args[-2]).read_bytes())
        return self.qpdf_code

    async def run(self, args: list[str], *, home: Path, timeout_seconds: float, label: str) -> int | None:
        self.calls.append(args)
        return await asyncio.to_thread(self._write, args, label)

    def labels(self) -> list[str]:
        return [Path(call[0]).name for call in self.calls]


def _install(monkeypatch: pytest.MonkeyPatch, tools: _Tools, *, gs: bool = True, qpdf: bool = True) -> None:
    monkeypatch.setattr(pdf_optimize, "_gs_binary", lambda: "/usr/bin/gs" if gs else None)
    monkeypatch.setattr(pdf_optimize, "_qpdf_binary", lambda: "/usr/bin/qpdf" if qpdf else None)
    monkeypatch.setattr(subprocess_guard, "run_isolated", tools.run)


def _slot(tmp_path: Path, key: str = "k") -> pdf_optimize.CacheSlot:
    return pdf_optimize.CacheSlot(str(tmp_path / "cache"), key, 10**9)


async def _prepare(tmp_path: Path, writer: _Writer, key: str = "k") -> bytes | None:
    path = await pdf_optimize.prepare_pdf_preview(writer, _slot(tmp_path, key), OPTIONS)
    return None if path is None else await asyncio.to_thread(path.read_bytes)


async def test_small_pdf_is_only_linearized_and_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = _Tools()
    _install(monkeypatch, tools)
    writer = _Writer(SMALL)
    assert await _prepare(tmp_path, writer) == b"LINEAR:" + SMALL
    assert tools.labels() == ["qpdf"]  # 没到压缩门槛，不跑 gs
    assert tools.calls[0][1] == "--linearize"
    # 第二次命中本地缓存：不再拉源文件、不再跑工具
    assert await _prepare(tmp_path, writer) == b"LINEAR:" + SMALL
    assert writer.calls == 1 and len(tools.calls) == 1


async def test_large_pdf_is_compressed_then_linearized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = _Tools(gs_keep=100)
    _install(monkeypatch, tools)
    assert await _prepare(tmp_path, _Writer(LARGE)) == b"LINEAR:" + LARGE[:100]
    assert tools.labels() == ["gs", "qpdf"]
    gs_args = tools.calls[0]
    assert "-dSAFER" in gs_args and "-sDEVICE=pdfwrite" in gs_args and "-dCompatibilityLevel=1.5" in gs_args
    assert "-dColorImageResolution=144" in gs_args and "-dGrayImageResolution=144" in gs_args
    assert "-dMonoImageResolution=288" in gs_args and "-dDownsampleMonoImages=true" in gs_args
    assert tools.calls[1][-2].endswith("compressed.pdf")  # 线性化的是压缩后的那份


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        (_Tools(gs_keep=10**6), b"LINEAR:" + LARGE),  # 没明显变小：不用压缩结果
        (_Tools(gs_code=1), b"LINEAR:" + LARGE),  # gs 失败：线性化原文件
        (_Tools(gs_code=None), b"LINEAR:" + LARGE),  # gs 超时：同上
        (_Tools(gs_code=None, qpdf_code=2), LARGE),  # 两步都失败：缓存原文件，预览照样能开
        (_Tools(gs_code=1, qpdf_code=3), b"LINEAR:" + LARGE),  # qpdf 有警告（退出码 3）输出照用
    ],
)
async def test_each_step_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tools: _Tools, expected: bytes
) -> None:
    _install(monkeypatch, tools)
    assert await _prepare(tmp_path, _Writer(LARGE)) == expected


async def test_without_tools_the_original_is_still_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = _Tools()
    _install(monkeypatch, tools, gs=False, qpdf=False)
    writer = _Writer(LARGE)
    assert await _prepare(tmp_path, writer) == LARGE
    assert tools.calls == []
    assert await _prepare(tmp_path, writer) == LARGE
    assert writer.calls == 1  # 之后的 Range 请求读本地盘，不再去对象存储拉整份


async def test_missing_source_and_cache_write_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install(monkeypatch, _Tools(), gs=False, qpdf=False)
    # 源文件不存在：返回 None，不记失败标记
    assert await _prepare(tmp_path, _Writer(None), key="gone") is None
    assert await preview_cache.failed_recently(str(tmp_path / "cache"), "gone") is False

    # 写缓存失败（如磁盘满）：记失败标记，10 分钟内直接回退、不再拉源文件重做
    async def broken_store(*_args: Any, **_kwargs: Any) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(preview_cache, "store", broken_store)
    writer = _Writer(SMALL)
    assert await _prepare(tmp_path, writer, key="full") is None
    assert await preview_cache.failed_recently(str(tmp_path / "cache"), "full") is True
    assert await _prepare(tmp_path, writer, key="full") is None
    assert writer.calls == 1


async def test_same_file_is_prepared_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = _Tools()
    _install(monkeypatch, tools)
    gate = asyncio.Event()
    original = tools.run

    async def slow(args: list[str], **kwargs: Any) -> int | None:
        await gate.wait()
        return await original(args, **kwargs)

    monkeypatch.setattr(subprocess_guard, "run_isolated", slow)
    writer = _Writer(SMALL)
    tasks = [asyncio.create_task(_prepare(tmp_path, writer)) for _ in range(3)]
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(*tasks)
    assert results == [b"LINEAR:" + SMALL] * 3
    assert writer.calls == 1 and len(tools.calls) == 1
    assert len(pdf_optimize._KEY_LOCKS) == 0


async def test_office_pdf_is_always_compressed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = _Tools(gs_keep=5)
    _install(monkeypatch, tools)
    monkeypatch.setattr(office_preview, "_soffice_binary", lambda: "/usr/bin/soffice")

    async def soffice(_binary: str, _input: Path, out_dir: Path, *_rest: Any) -> Path:
        out = out_dir / "source.pdf"
        await asyncio.to_thread(out.write_bytes, SMALL)
        return out

    monkeypatch.setattr(office_preview, "_run_soffice", soffice)
    path = await office_preview.convert_office_to_pdf(
        _Writer(b"pptx"), "PPTX", cache_dir=str(tmp_path / "c"), cache_key="o", max_cache_bytes=10**9, optimize=OPTIONS
    )
    assert path is not None
    assert await asyncio.to_thread(path.read_bytes) == b"LINEAR:" + SMALL[:5]
    assert tools.labels() == ["gs", "qpdf"]  # 小于门槛也压：LibreOffice 转出的图片常是原分辨率


async def test_run_isolated_runs_and_times_out(tmp_path: Path) -> None:
    ok = [sys.executable, "-c", "import sys; sys.exit(3)"]
    assert await subprocess_guard.run_isolated(ok, home=tmp_path, timeout_seconds=30, label="t") == 3
    hang = [sys.executable, "-c", "import time; time.sleep(1)"]
    assert await subprocess_guard.run_isolated(hang, home=tmp_path, timeout_seconds=0.05, label="t") is None


def test_child_env_drops_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THINKTANK_MINIO_SECRET_KEY", "secret")
    env = subprocess_guard.child_env(tmp_path)
    assert "THINKTANK_MINIO_SECRET_KEY" not in env
    assert env["HOME"] == str(tmp_path)
