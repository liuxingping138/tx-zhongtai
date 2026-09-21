"""操作者身份。业务服务从鉴权结果构造，用于审计留痕。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
