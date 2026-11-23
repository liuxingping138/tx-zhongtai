"""预览相关测试共用的配置和打桩。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import pdf_optimize


def preview_settings(storage_dir: Path, **overrides: object) -> SimpleNamespace:
    """预览要用到的那几项配置，默认值同 Settings。"""

    values: dict[str, object] = {
        "storage_dir": str(storage_dir),
        "minio_endpoint": "",
        "preview_cache_max_bytes": 10**9,
        "preview_compress_min_bytes": 3 * 1024 * 1024,
        "preview_compress_dpi": 144,
        "preview_optimize_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def no_pdf_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """当作没装 gs / qpdf：开发机上装了也不在单测里真的去跑。"""

    monkeypatch.setattr(pdf_optimize, "_gs_binary", lambda: None)
    monkeypatch.setattr(pdf_optimize, "_qpdf_binary", lambda: None)
