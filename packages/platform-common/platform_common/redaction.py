"""敏感字段脱敏。全平台唯一一份键名清单。

禁止记录的内容（架构文档第 10.3 节）：明文密码、完整 Token、Cookie、
Authorization 头、密钥、完整请求体。

以前日志、iam 的 Outbox 投递、audit 的入库与查询各自维护一份清单，
已经漂移出差异：日志那份有 jwt / id_token / client_secret，两个服务那份没有；
两个服务那份有 internal_token，日志那份的递归又漏了 list。合成一份，
新增敏感字段只改这里。

按**键名**脱敏，拦不住把敏感值拼进字符串的写法
（`logger.info("失败", detail="password=xxx")`），业务代码仍要自觉。
"""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "old_password",
        "new_password",
        "temporary_password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "internal_token",
        "authorization",
        "cookie",
        "set-cookie",
        "secret",
        "client_secret",
        "private_key",
        "jwt",
        "csrf_token",
    }
)

REDACTED = "***REDACTED***"


def redact(value: Any, key: str | None = None) -> Any:
    """递归脱敏 dict 和 list。键名命中即整个值被替换。"""

    if key and key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
