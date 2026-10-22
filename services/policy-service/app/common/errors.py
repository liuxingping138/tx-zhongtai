"""能原样显示给页面的执行失败原因。其他异常只显示类型名，避免把连接串、SQL 参数透到页面。"""

from __future__ import annotations


class UserFacingError(RuntimeError):
    pass
