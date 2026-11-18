"""从码表服务拉取省市区码表里的权威省份列表，不可用时回退内置省列表。"""

from __future__ import annotations

import time
from typing import Protocol

import httpx
from platform_common.internal_calls import internal_headers
from platform_common.logging_setup import get_logger

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 300.0
_cache: dict[str, tuple[float, list[str]]] = {}


class CodebookSettings(Protocol):
    codebook_base_url: str
    codebook_service_secret: str
    codebook_timeout_seconds: float


def clear_province_cache() -> None:
    _cache.clear()


def _merge_provinces(raw_items: list[str], fallback: tuple[str, ...]) -> list[str]:
    cleaned = [str(item).strip() for item in raw_items if str(item).strip()]
    if not cleaned:
        return list(fallback)
    # 知识库包含总部文件，首项保留「集团」再接码表省级列表
    merged = ["集团"]
    for name in cleaned:
        if name != "集团" and name not in merged:
            merged.append(name)
    return merged


async def get_provinces(settings: CodebookSettings, fallback: tuple[str, ...]) -> list[str]:
    base_url = (getattr(settings, "codebook_base_url", "") or "").strip().rstrip("/")
    secret = (getattr(settings, "codebook_service_secret", "") or "").strip()
    if not base_url or not secret:
        return list(fallback)

    now = time.monotonic()
    cached = _cache.get(base_url)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return list(cached[1])

    try:
        async with httpx.AsyncClient(timeout=settings.codebook_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/internal/v1/provinces",
                headers=internal_headers("thinktank-service", secret),
            )
            resp.raise_for_status()
            payload = resp.json()
        items = (payload.get("data") or {}).get("items") or []
        merged = _merge_provinces(items, fallback)
        _cache[base_url] = (now, merged)
        return list(merged)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("codebook_provinces_fallback", error=str(exc))
        return list(fallback)
