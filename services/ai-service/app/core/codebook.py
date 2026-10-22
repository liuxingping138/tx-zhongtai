"""码表服务的内部接口客户端：AI 模板引用系统码表时实时取最新内容。"""

from __future__ import annotations

import httpx
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode
from platform_common.internal_calls import internal_headers

from app.core.config import get_settings


async def fetch_code_table(name: str) -> str:
    """返回制表符文本（首行表头）。取不到就报错，不能拿空码表去提问——模型会照样回答，结果全错。"""

    settings = get_settings()
    if not settings.codebook_service_secret:
        raise DependencyUnavailableError("未配置码表服务的内部调用密钥，暂不能使用系统码表")
    try:
        async with httpx.AsyncClient(
            base_url=settings.codebook_base_url, timeout=settings.codebook_timeout_seconds
        ) as client:
            response = await client.get(
                f"/internal/v1/code-tables/{name}",
                headers=internal_headers(settings.service_name, settings.codebook_service_secret),
            )
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError("码表服务暂时不可用，请稍后重试") from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        raise ApiError(f"码表服务没有「{name}」这张码表", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if response.status_code != httpx.codes.OK:
        raise DependencyUnavailableError(f"码表服务拒绝了请求（HTTP {response.status_code}）")
    return str(response.json()["data"]["text"])
