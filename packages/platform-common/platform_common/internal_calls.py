"""服务间内部调用：调用方带服务名和共享密钥，被调方按「服务名 -> 密钥」表逐个核对。

内部接口一律放在 `/internal/` 前缀下，网关不声明这个前缀，外部访问不到。
"""

from __future__ import annotations

import hmac

from fastapi import Request

from platform_common.errors import InternalCallerRejectedError

SERVICE_HEADER = "X-Internal-Service"
CREDENTIAL_HEADER = "X-Internal-Token"


def internal_headers(service_name: str, secret: str) -> dict[str, str]:
    return {SERVICE_HEADER: service_name, CREDENTIAL_HEADER: secret}


def verify_internal_caller(request: Request, secrets: dict[str, str]) -> str:
    """核对调用方，返回调用方服务名。没配密钥的服务一律拒绝；比较用定长时间，不泄露密钥前缀。"""

    service = (request.headers.get(SERVICE_HEADER) or "").strip()
    given = (request.headers.get(CREDENTIAL_HEADER) or "").encode()
    wanted = (secrets.get(service) or "").encode()
    if not service or not wanted or len(given) != len(wanted) or not hmac.compare_digest(given, wanted):
        raise InternalCallerRejectedError()
    return service
