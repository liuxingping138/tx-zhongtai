"""能原样显示给页面的执行失败原因。其他异常只显示类型名，避免把连接串、SQL 参数透到页面。

定义在公共调度引擎里：引擎据它判断「重试也没用、直接失败」。
"""

from __future__ import annotations

from platform_common.scheduler import UserFacingError

__all__ = ["UserFacingError"]
