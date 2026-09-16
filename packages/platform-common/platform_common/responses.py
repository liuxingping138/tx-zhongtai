"""统一响应包装：成功响应、分页结构。

失败响应由 `platform_common.errors` 中的异常处理器统一生成，
与本模块的 `ApiResponse` 使用同一个 JSON 形状：
    {"code": "OK", "message": "success", "data": ..., "request_id": "..."}
"""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class Page[T](BaseModel):
    """分页列表数据结构，配合 `ApiResponse` 使用。"""

    items: list[T]
    total: int
    page: int = Field(default=DEFAULT_PAGE, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class ApiResponse[T](BaseModel):
    """统一成功响应包装。错误响应见 `platform_common.errors`。"""

    code: str = "OK"
    message: str = "success"
    data: T | None = None
    request_id: str | None = None


def ok[T](data: T | None = None, *, request_id: str | None = None, message: str = "success") -> ApiResponse[T]:
    """构造统一成功响应。"""

    return ApiResponse[T](code="OK", message=message, data=data, request_id=request_id)


def paginate[T](
    items: list[T],
    total: int,
    *,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Page[T]:
    """构造分页数据结构。调用方需自行保证 `page`/`page_size` 已按白名单校验。"""

    return Page[T](items=items, total=total, page=page, page_size=page_size)
