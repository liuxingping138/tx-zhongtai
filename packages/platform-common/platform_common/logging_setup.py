"""结构化日志初始化，统一 JSON 格式并对敏感字段脱敏。

敏感键名清单在 platform_common.redaction，全平台共用一份。
本模块只负责把它接进 structlog 的处理链；业务代码仍需自行避免把敏感值
拼进日志消息本身，按键名脱敏拦不住那种写法。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from platform_common.redaction import redact
from platform_common.request_context import get_request_id


def _redaction_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {key: redact(value, key) for key, value in event_dict.items()}


def _inject_request_id(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    request_id = get_request_id()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


def setup_logging(service_name: str, *, level: str = "INFO", json_output: bool = True) -> None:
    """初始化 structlog + 标准库日志，服务启动时调用一次。"""

    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redaction_processor,
    ]

    renderer: Any = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]

    structlog.get_logger(service_name).info("logging_initialized", service=service_name, level=level)


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
