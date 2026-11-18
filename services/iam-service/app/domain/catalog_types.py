"""权限目录规格数据类。与 catalog / thinktank_catalog 共用，避免循环导入。"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import GrantLevel, NodeType


@dataclass(frozen=True)
class ResourceSpec:
    code: str
    name: str
    service_code: str
    node_type: NodeType
    published: bool
    sort_order: int
    parent_code: str | None = None


@dataclass(frozen=True)
class ActionSpec:
    resource_code: str
    action_code: str
    required_level: GrantLevel


@dataclass(frozen=True)
class MenuSpec:
    code: str
    title: str
    sort_order: int
    route_name: str | None = None
    resource_code: str | None = None
    parent_code: str | None = None
    icon: str | None = None
    enabled: bool = True
