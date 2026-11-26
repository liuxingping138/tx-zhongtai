"""码表服务的内部接口客户端：AI 模板引用系统码表时实时取最新内容。"""

from __future__ import annotations

from typing import Any

import httpx
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode
from platform_common.internal_calls import internal_headers

from app.core.config import get_settings

# 码表服务按服务名核对密钥；ai-worker 和 ai-service 是同一服务的两个进程，固定报 ai-service，不跟进程名走。
CALLER = "ai-service"
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)
_client: httpx.AsyncClient | None = None
_client_factory: Any = None


def _get_client() -> httpx.AsyncClient:
    global _client, _client_factory  # noqa: PLW0603  进程级连接池复用，停服时通过 close_codebook_client 释放
    if _client is None or _client.is_closed or _client_factory is not httpx.AsyncClient:
        _client = httpx.AsyncClient(limits=_HTTP_LIMITS)
        _client_factory = httpx.AsyncClient
    return _client


async def close_codebook_client() -> None:
    global _client, _client_factory  # noqa: PLW0603  停服时释放进程级 HTTP 连接池
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_factory = None


async def fetch_code_table(name: str) -> str:
    """返回制表符文本（首行表头）。取不到就报错，不能拿空码表去提问——模型会照样回答，结果全错。"""

    settings = get_settings()
    if not settings.codebook_service_secret:
        raise DependencyUnavailableError("未配置码表服务的内部调用密钥，暂不能使用系统码表")
    url = f"{settings.codebook_base_url.rstrip('/')}/internal/v1/code-tables/{name}"
    try:
        response = await _get_client().get(
            url,
            headers=internal_headers(CALLER, settings.codebook_service_secret),
            timeout=settings.codebook_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError("码表服务暂时不可用，请稍后重试") from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        raise ApiError(f"码表服务没有「{name}」这张码表", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if response.status_code != httpx.codes.OK:
        raise DependencyUnavailableError(f"码表服务拒绝了请求（HTTP {response.status_code}）")
    return str(response.json()["data"]["text"])
