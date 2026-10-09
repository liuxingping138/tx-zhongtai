"""跨服务鉴权客户端。依赖失败必须返回 503，不能当作允许。"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import httpx

from platform_common.errors import (
    DependencyUnavailableError,
    ErrorCode,
    PermissionDeniedError,
    UnauthenticatedError,
)
from platform_common.logging_setup import get_logger

logger = get_logger("platform_common.authz")


def _error_code(response: httpx.Response) -> str | None:
    try:
        raw: Any = response.json()
    except ValueError:
        return None
    code = raw.get("code") if isinstance(raw, dict) else None
    return code if isinstance(code, str) else None


@dataclass(frozen=True)
class AuthzResult:
    allowed: bool
    user_id: str | None
    username: str | None
    display_name: str | None
    level: str | None
    reason: str | None


class AuthzClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_name: str,
        service_secret: str,
        timeout_seconds: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service_name = service_name
        self._service_secret = service_secret
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def authorize(self, *, access_token: str, resource: str, action: str) -> AuthzResult:
        try:
            response = await self._client.post(
                "/internal/v1/authorize",
                json={"access_token": access_token, "resource": resource, "action": action},
                headers={
                    "X-Internal-Service": self._service_name,
                    "X-Internal-Token": self._service_secret,
                },
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError("鉴权服务暂时不可用") from exc

        if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise DependencyUnavailableError("鉴权服务暂时不可用")
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            if _error_code(response) == ErrorCode.INTERNAL_CALLER_REJECTED:
                # 本服务的内部密钥配错了。当成「用户未登录」会让前端反复刷新会话再报错，
                # 真正的原因却藏起来；按依赖不可用返回 503，并留日志给运维。
                logger.error("authz_internal_caller_rejected", service=self._service_name)
                raise DependencyUnavailableError("鉴权服务拒绝了本服务的内部调用凭据")
            raise UnauthenticatedError()
        if response.status_code == HTTPStatus.FORBIDDEN:
            raise PermissionDeniedError()

        try:
            raw: Any = response.json()
        except ValueError as exc:
            raise DependencyUnavailableError("鉴权服务响应无效") from exc

        payload = raw.get("data") if isinstance(raw, dict) else None
        data: dict[str, Any] = payload if isinstance(payload, dict) else raw if isinstance(raw, dict) else {}
        allowed = bool(data.get("allowed"))
        if not allowed:
            reason = data.get("reason")
            raise PermissionDeniedError(reason if isinstance(reason, str) and reason else "没有执行该操作的权限")

        user_raw = data.get("user")
        user: dict[str, Any] = user_raw if isinstance(user_raw, dict) else {}
        user_id = user.get("id")
        username = user.get("username")
        display_name = user.get("display_name")
        level = data.get("level")
        return AuthzResult(
            allowed=True,
            user_id=user_id if isinstance(user_id, str) else None,
            username=username if isinstance(username, str) else None,
            display_name=display_name if isinstance(display_name, str) else None,
            level=level if isinstance(level, str) else None,
            reason=None,
        )
