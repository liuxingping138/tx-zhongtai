"""调用其他服务的 /internal/ 接口：ai-service（用上线模板跑批）和 codebook-service（取码表）。

依赖失败一律抛 DependencyUnavailableError，调用方据此把这次执行记成失败，不能当成「没有数据」。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode
from platform_common.internal_calls import internal_headers

from app.core.config import get_settings

# 对方按服务名核对密钥。policy-worker 和 policy-service 是同一个服务的两个进程（worker 的 service_name 是
# policy-worker），打标在 worker 里跑，所以这里固定报 policy-service，不跟进程名走。
CALLER = "policy-service"
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)
_client: httpx.AsyncClient | None = None
_client_factory: Any = None


def _get_client() -> httpx.AsyncClient:
    global _client, _client_factory  # noqa: PLW0603  进程级连接池复用，停服时通过 close_internal_clients 释放
    if _client is None or _client.is_closed or _client_factory is not httpx.AsyncClient:
        _client = httpx.AsyncClient(limits=_HTTP_LIMITS)
        _client_factory = httpx.AsyncClient
    return _client


async def close_internal_clients() -> None:
    global _client, _client_factory  # noqa: PLW0603  停服时释放进程级 HTTP 连接池
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_factory = None


async def _call(
    base_url: str, secret: str, method: str, path: str, *, request_timeout: float | None = None, **kwargs: Any
) -> Any:
    settings = get_settings()
    if not secret:
        raise DependencyUnavailableError(f"未配置调用 {base_url} 的内部密钥")
    headers = internal_headers(CALLER, secret)
    if "json" in kwargs:
        # 汉字按 UTF-8 原样发：httpx 默认转义成 \uXXXX，一个字 6 字节，一批政策正文就会超过对方的请求体上限。
        kwargs["content"] = json.dumps(kwargs.pop("json"), ensure_ascii=False).encode()
        headers = {**headers, "content-type": "application/json"}
    url = f"{base_url.rstrip('/')}{path}"
    timeout = request_timeout or settings.internal_timeout_seconds
    try:
        response = await _get_client().request(method, url, headers=headers, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError(f"{base_url} 暂时不可用") from exc
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code >= httpx.codes.BAD_REQUEST:
        message = body.get("message") if isinstance(body, dict) else None
        if response.status_code in {httpx.codes.UNPROCESSABLE_ENTITY, httpx.codes.CONFLICT}:
            raise ApiError(str(message or "请求被拒绝"), code=ErrorCode.VALIDATION_ERROR, http_status=422)
        raise DependencyUnavailableError(f"{base_url}{path} 返回 HTTP {response.status_code}：{message or ''}")
    return body.get("data") if isinstance(body, dict) else None


async def ai(method: str, path: str, **kwargs: Any) -> Any:
    settings = get_settings()
    return await _call(settings.ai_base_url, settings.ai_service_secret, method, path, **kwargs)


async def codebook(method: str, path: str, **kwargs: Any) -> Any:
    settings = get_settings()
    return await _call(settings.codebook_base_url, settings.codebook_service_secret, method, path, **kwargs)


async def _code_table_rows(name: str) -> list[list[str]]:
    """码表服务给的是带表头的制表符文本，去掉表头按列拆开。"""

    data = await codebook("GET", f"/internal/v1/code-tables/{name}")
    lines = str(data["text"]).split("\n")[1:]
    return [[cell.strip() for cell in line.split("\t")] for line in lines if line.strip()]


def _column(rows: list[list[str]], index: int) -> list[str]:
    """某一列去空、去重，保持码表顺序。"""

    return list(dict.fromkeys(row[index] for row in rows if len(row) > index and row[index]))


async def policy_type_names() -> list[str]:
    """政策类型码表里的类型名称。AI 打标核对类型、列表的政策类型筛选项都用它。"""

    return _column(await _code_table_rows("policy_types"), 0)


async def scenario_l1_names() -> tuple[list[str], list[str]]:
    """行业场景码表的一级行业、一级场景名称，政策解读列表的筛选项用它，不在几百万条解读上去重。"""

    rows = await _code_table_rows("scenario_l1")
    return _column(rows, 0), _column(rows, 1)
