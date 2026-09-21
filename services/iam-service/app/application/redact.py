"""Outbox 投递前脱敏，避免密码、令牌进入审计库。

键名清单已下沉到 platform_common.redaction，这里只做转发，
保持既有导入路径不变。新增敏感字段改公共模块。
"""

from __future__ import annotations

from platform_common.redaction import REDACTED, SENSITIVE_KEYS, redact

__all__ = ["REDACTED", "SENSITIVE_KEYS", "redact"]
