"""跨服务鉴权客户端。依赖失败必须返回 503，不能当作允许。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import httpx

from platform_common.errors import (
    DependencyUnavailableError,
    ErrorCode,
    NetworkDeniedError,
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


def _error_message(response: httpx.Response) -> str | None:
    try:
        raw: Any = response.json()
    except ValueError:
        return None
    message = raw.get("message") if isinstance(raw, dict) else None
    return message if isinstance(message, str) and message else None


@dataclass(frozen=True)
class AuthzResult:
    allowed: bool
    user_id: str | None
    username: str | None
    display_name: str | None
    level: str | None
    reason: str | None
    scopes: dict[str, str] | None = None


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

    def _raise_for_status(self, response: httpx.Response) -> None:
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
            if _error_code(response) == ErrorCode.NETWORK_DENIED:
                # 不是没权限，是网络不对：原样带上 IAM 的说明（里面有来源 IP），前端据此跳说明页。
                raise NetworkDeniedError(_error_message(response) or NetworkDeniedError.default_message)
            raise PermissionDeniedError()
        if not response.is_success:
            # 404、422 这类是部署错路由或版本不配，不是用户没权限：当成「无权限」会把排障引到授权上去。
            logger.error("authz_unexpected_response", service=self._service_name, status=response.status_code)
            raise DependencyUnavailableError(f"鉴权服务响应异常（HTTP {response.status_code}）")

    async def authorize(
        self,
        *,
        access_token: str,
        resource: str,
        action: str,
        scope_prefixes: Sequence[str] | None = None,
        client_ip: str | None = None,
    ) -> AuthzResult:
        body: dict[str, Any] = {"access_token": access_token, "resource": resource, "action": action}
        if scope_prefixes:
            body["scope_prefixes"] = list(scope_prefixes)
        # 带上来源 IP，IAM 才能对限定网络的模块（如智库）核对公司网络和访问白名单。
        if client_ip:
            body["client_ip"] = client_ip
        try:
            response = await self._client.post(
                "/internal/v1/authorize",
                json=body,
                headers={
                    "X-Internal-Service": self._service_name,
                    "X-Internal-Token": self._service_secret,
                },
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError("鉴权服务暂时不可用") from exc

        self._raise_for_status(response)

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
        raw_scopes = data.get("scopes")
        scopes = (
            {str(k): str(v) for k, v in raw_scopes.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(raw_scopes, dict)
            else None
        )
        return AuthzResult(
            allowed=True,
            user_id=user_id if isinstance(user_id, str) else None,
            username=username if isinstance(username, str) else None,
            display_name=display_name if isinstance(display_name, str) else None,
            level=level if isinstance(level, str) else None,
            reason=None,
            scopes=scopes,
        )
