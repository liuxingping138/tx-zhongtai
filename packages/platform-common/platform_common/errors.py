"""统一错误码与异常处理器。

所有失败响应使用与 `platform_common.responses.ApiResponse` 相同的 JSON 形状：
    {"code": "...", "message": "...", "data": null, "request_id": "..."}

真实 HTTP 状态码语义遵循架构文档第 11.1 节：
400 参数语义错误、401 未认证、403 无权限、404 不存在、409 冲突、
422 校验失败、429 限流、503 依赖不可用。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from platform_common.request_context import get_request_id

logger = logging.getLogger("platform_common.errors")


class ErrorCode:
    """错误码常量。业务服务可以在自己的模块内扩展专属错误码，但公共码固定不变。"""

    OK = "OK"
    BAD_REQUEST = "BAD_REQUEST"
    AUTH_UNAUTHENTICATED = "AUTH_UNAUTHENTICATED"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    # 服务间调用的内部凭据不对。这是部署配置错误，不是终端用户没登录，调用方要转成 503。
    INTERNAL_CALLER_REJECTED = "INTERNAL_CALLER_REJECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """统一业务异常基类。服务内应优先抛出该异常的子类，而不是直接抛 HTTPException。"""

    http_status: int = status.HTTP_400_BAD_REQUEST
    code: str = ErrorCode.BAD_REQUEST

    def __init__(self, message: str, *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class UnauthenticatedError(ApiError):
    http_status = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.AUTH_UNAUTHENTICATED

    def __init__(self, message: str = "未认证或凭据已失效") -> None:
        super().__init__(message)


class InternalCallerRejectedError(ApiError):
    """内部接口的调用方凭据不对。仍回 401，但用独立错误码，调用方据此区分「配置错」和「用户未登录」。"""

    http_status = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.INTERNAL_CALLER_REJECTED

    def __init__(self, message: str = "内部调用凭据无效") -> None:
        super().__init__(message)


class PermissionDeniedError(ApiError):
    http_status = status.HTTP_403_FORBIDDEN
    code = ErrorCode.AUTH_PERMISSION_DENIED

    def __init__(self, message: str = "没有执行该操作的权限") -> None:
        super().__init__(message)


class NotFoundError(ApiError):
    http_status = status.HTTP_404_NOT_FOUND
    code = ErrorCode.RESOURCE_NOT_FOUND

    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(message)


class VersionConflictError(ApiError):
    http_status = status.HTTP_409_CONFLICT
    code = ErrorCode.VERSION_CONFLICT

    def __init__(self, message: str = "数据已被修改，请刷新后重试") -> None:
        super().__init__(message)


class RateLimitedError(ApiError):
    http_status = status.HTTP_429_TOO_MANY_REQUESTS
    code = ErrorCode.RATE_LIMITED

    def __init__(self, message: str = "请求过于频繁，请稍后重试", *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class DependencyUnavailableError(ApiError):
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.DEPENDENCY_UNAVAILABLE

    def __init__(self, message: str = "依赖服务暂时不可用，请稍后重试") -> None:
        super().__init__(message)


# PostgreSQL 唯一约束冲突。
UNIQUE_VIOLATION = "23505"


def is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION


def _error_body(code: str, message: str, request_id: str | None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": None, "request_id": request_id}


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理器。必须在应用启动时调用一次。"""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitedError) and exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, get_request_id()),
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        detail = "请求参数校验失败"
        if first:
            loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
            detail = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_body(ErrorCode.VALIDATION_ERROR, detail, get_request_id()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTH_UNAUTHENTICATED,
            status.HTTP_403_FORBIDDEN: ErrorCode.AUTH_PERMISSION_DENIED,
            status.HTTP_404_NOT_FOUND: ErrorCode.RESOURCE_NOT_FOUND,
            status.HTTP_409_CONFLICT: ErrorCode.VERSION_CONFLICT,
            status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
            status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.DEPENDENCY_UNAVAILABLE,
        }
        default_code = (
            ErrorCode.INTERNAL_ERROR if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR else ErrorCode.BAD_REQUEST
        )
        code = code_map.get(exc.status_code, default_code)
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message, get_request_id()),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        """并发新增撞上唯一约束时回 409，而不是 500。

        业务层「先查重再插入」挡不住两个请求同时通过查重，最后由数据库唯一约束兜底。
        这属于可预期的冲突，用户刷新后重试即可。非空、外键等其他完整性错误说明代码有缺陷，
        仍按 500 记录，避免被当成普通冲突掩盖。
        """

        request_id = get_request_id()
        if not is_unique_violation(exc):
            logger.exception("完整性约束异常 request_id=%s", request_id)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_error_body(ErrorCode.INTERNAL_ERROR, "服务器内部错误，请联系管理员", request_id),
            )
        logger.info("唯一约束冲突 request_id=%s", request_id)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_body(
                ErrorCode.VERSION_CONFLICT, "与已有记录重复，可能刚被他人新增，请刷新后重试", request_id
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id()
        logger.exception("未捕获异常 request_id=%s", request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(ErrorCode.INTERNAL_ERROR, "服务器内部错误，请联系管理员", request_id),
        )


HandlerType = Callable[[Request, Exception], Awaitable[JSONResponse]]
