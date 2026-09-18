"""随代码发布的资源 / 动作 / 菜单清单。

未交付业务资源 published=false。码表管理已按用户提供的 Excel 发布。
清单同步必须幂等。
"""

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


RESOURCE_SPECS: tuple[ResourceSpec, ...] = (
    ResourceSpec("system", "系统管理", "iam-service", NodeType.DIRECTORY, True, 10),
    ResourceSpec("system.users", "用户管理", "iam-service", NodeType.RESOURCE, True, 11, "system"),
    ResourceSpec("system.roles", "角色管理", "iam-service", NodeType.RESOURCE, True, 12, "system"),
    ResourceSpec("system.permissions", "权限分配", "iam-service", NodeType.RESOURCE, True, 13, "system"),
    ResourceSpec("system.audit", "审计查询", "iam-service", NodeType.RESOURCE, True, 14, "system"),
    ResourceSpec("policy", "政策", "policy-service", NodeType.DIRECTORY, False, 20),
    ResourceSpec("policy.sources", "信源配置", "policy-service", NodeType.RESOURCE, False, 21, "policy"),
    ResourceSpec(
        "policy.crawler_monitoring", "爬虫监测", "policy-service", NodeType.RESOURCE, False, 22, "policy"
    ),
    ResourceSpec("policy.interpretations", "政策解读列表", "policy-service", NodeType.RESOURCE, False, 23, "policy"),
    ResourceSpec("policy.base_tags", "政策基础标签表", "policy-service", NodeType.RESOURCE, False, 24, "policy"),
    ResourceSpec("customer", "客户", "customer-service", NodeType.RESOURCE, False, 30),
    ResourceSpec("tender", "招投标", "tender-service", NodeType.RESOURCE, False, 40),
    ResourceSpec("codebook", "码表管理", "codebook-service", NodeType.DIRECTORY, True, 50),
    ResourceSpec(
        "codebook.policy_types", "政策类型码表", "codebook-service", NodeType.RESOURCE, True, 51, "codebook"
    ),
    ResourceSpec("codebook.scenarios", "场景码表", "codebook-service", NodeType.RESOURCE, True, 52, "codebook"),
)

ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec("system.users", "list", GrantLevel.READ),
    ActionSpec("system.users", "read", GrantLevel.READ),
    ActionSpec("system.users", "create", GrantLevel.FULL),
    ActionSpec("system.users", "update", GrantLevel.FULL),
    ActionSpec("system.users", "reset_password", GrantLevel.FULL),
    ActionSpec("system.users", "revoke_sessions", GrantLevel.FULL),
    ActionSpec("system.roles", "list", GrantLevel.READ),
    ActionSpec("system.roles", "read", GrantLevel.READ),
    ActionSpec("system.roles", "create", GrantLevel.FULL),
    ActionSpec("system.roles", "update", GrantLevel.FULL),
    ActionSpec("system.permissions", "read", GrantLevel.READ),
    ActionSpec("system.permissions", "grant", GrantLevel.FULL),
    ActionSpec("system.audit", "list", GrantLevel.READ),
    ActionSpec("system.audit", "read", GrantLevel.READ),
    ActionSpec("codebook.policy_types", "list", GrantLevel.READ),
    ActionSpec("codebook.policy_types", "read", GrantLevel.READ),
    ActionSpec("codebook.policy_types", "export", GrantLevel.READ),
    ActionSpec("codebook.policy_types", "create", GrantLevel.FULL),
    ActionSpec("codebook.policy_types", "update", GrantLevel.FULL),
    ActionSpec("codebook.policy_types", "import", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "list", GrantLevel.READ),
    ActionSpec("codebook.scenarios", "read", GrantLevel.READ),
    ActionSpec("codebook.scenarios", "export", GrantLevel.READ),
    ActionSpec("codebook.scenarios", "create", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "update", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "import", GrantLevel.FULL),
)

MENU_SPECS: tuple[MenuSpec, ...] = (
    MenuSpec("menu.system", "系统管理", 10, icon="setting"),
    MenuSpec("menu.system.users", "用户管理", 11, "system-users", "system.users", "menu.system"),
    MenuSpec("menu.system.roles", "角色管理", 12, "system-roles", "system.roles", "menu.system"),
    MenuSpec("menu.system.permissions", "权限分配", 13, "system-permissions", "system.permissions", "menu.system"),
    MenuSpec("menu.system.audit", "操作日志", 14, "system-audit", "system.audit", "menu.system"),
    MenuSpec("menu.policy", "政策", 20, enabled=False),
    MenuSpec("menu.policy.sources", "信源配置", 21, "policy-sources", "policy.sources", "menu.policy", enabled=False),
    MenuSpec(
        "menu.policy.crawler",
        "爬虫监测",
        22,
        "policy-crawler-monitoring",
        "policy.crawler_monitoring",
        "menu.policy",
        enabled=False,
    ),
    MenuSpec(
        "menu.policy.interpretations",
        "政策解读列表",
        23,
        "policy-interpretations",
        "policy.interpretations",
        "menu.policy",
        enabled=False,
    ),
    MenuSpec(
        "menu.policy.base_tags",
        "政策基础标签表",
        24,
        "policy-base-tags",
        "policy.base_tags",
        "menu.policy",
        enabled=False,
    ),
    MenuSpec("menu.customer", "客户", 30, "customer", "customer", enabled=False),
    MenuSpec("menu.tender", "招投标", 40, "tender", "tender", enabled=False),
    MenuSpec("menu.codebook", "码表管理", 50, enabled=True),
    MenuSpec(
        "menu.codebook.policy_types",
        "政策类型码表",
        51,
        "codebook-policy-types",
        "codebook.policy_types",
        "menu.codebook",
        enabled=True,
    ),
    MenuSpec(
        "menu.codebook.scenarios",
        "场景码表",
        52,
        "codebook-scenarios",
        "codebook.scenarios",
        "menu.codebook",
        enabled=True,
    ),
)

SUPERADMIN_ROLE_CODE = "superadmin"
SUPERADMIN_ROLE_NAME = "超级管理员"
