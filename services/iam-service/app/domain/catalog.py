"""随代码发布的资源 / 动作 / 菜单清单。

未交付业务资源 published=false。码表与政策三个子模块已按用户提供的 Excel 发布。
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


# 已下线的资源：同步清单时连同它的菜单、授权和动作一起清掉，否则角色权限页还会列出已不存在的模块。
# 只放真正下线的编码；改名用迁移原地改，不能写在这里，否则授权会被删掉。
RETIRED_RESOURCE_CODES: tuple[str, ...] = ()

RESOURCE_SPECS: tuple[ResourceSpec, ...] = (
    ResourceSpec("system", "系统管理", "iam-service", NodeType.DIRECTORY, True, 10),
    ResourceSpec("system.users", "用户管理", "iam-service", NodeType.RESOURCE, True, 11, "system"),
    ResourceSpec("system.roles", "角色与权限", "iam-service", NodeType.RESOURCE, True, 12, "system"),
    ResourceSpec("system.permissions", "权限分配", "iam-service", NodeType.RESOURCE, True, 13, "system"),
    ResourceSpec("system.scheduler", "任务调度", "policy-service", NodeType.RESOURCE, True, 15, "system"),
    ResourceSpec("system.audit", "操作日志", "iam-service", NodeType.RESOURCE, True, 14, "system"),
    ResourceSpec("policy", "政策", "policy-service", NodeType.DIRECTORY, True, 20),
    ResourceSpec("policy.sources", "信源管理", "policy-service", NodeType.RESOURCE, True, 21, "policy"),
    ResourceSpec("policy.crawler_monitoring", "爬虫监测", "policy-service", NodeType.RESOURCE, True, 22, "policy"),
    ResourceSpec("policy.interpretations", "政策解读列表", "policy-service", NodeType.RESOURCE, True, 23, "policy"),
    ResourceSpec("policy.base_tags", "政策基础标签表", "policy-service", NodeType.RESOURCE, True, 24, "policy"),
    ResourceSpec("customer", "客户", "customer-service", NodeType.RESOURCE, False, 30),
    ResourceSpec("tender", "招投标", "tender-service", NodeType.RESOURCE, False, 40),
    ResourceSpec("codebook", "码表管理", "codebook-service", NodeType.DIRECTORY, True, 50),
    ResourceSpec("codebook.policy_types", "政策类型码表", "codebook-service", NodeType.RESOURCE, True, 51, "codebook"),
    ResourceSpec("codebook.scenarios", "行业场景码表", "codebook-service", NodeType.RESOURCE, True, 52, "codebook"),
    ResourceSpec("codebook.area_codes", "省市区编码表", "codebook-service", NodeType.RESOURCE, True, 53, "codebook"),
    ResourceSpec("ai", "AI 打表", "ai-service", NodeType.DIRECTORY, True, 60),
    ResourceSpec("ai.prompts", "提问配置", "ai-service", NodeType.RESOURCE, True, 61, "ai"),
    ResourceSpec("ai.batch_runs", "批量提问", "ai-service", NodeType.RESOURCE, True, 62, "ai"),
    ResourceSpec("ai.chat", "多轮对话", "ai-service", NodeType.RESOURCE, True, 63, "ai"),
)

ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec("system.scheduler", "list", GrantLevel.READ),
    ActionSpec("system.scheduler", "update", GrantLevel.FULL),
    ActionSpec("system.scheduler", "execute", GrantLevel.FULL),
    ActionSpec("system.users", "list", GrantLevel.READ),
    ActionSpec("system.users", "read", GrantLevel.READ),
    ActionSpec("system.users", "create", GrantLevel.FULL),
    ActionSpec("system.users", "update", GrantLevel.FULL),
    ActionSpec("system.users", "reset_password", GrantLevel.FULL),
    ActionSpec("system.users", "revoke_sessions", GrantLevel.FULL),
    ActionSpec("system.users", "delete", GrantLevel.FULL),
    ActionSpec("system.users", "export", GrantLevel.EXPORT),
    ActionSpec("system.users", "import", GrantLevel.FULL),
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
    ActionSpec("codebook.policy_types", "export", GrantLevel.EXPORT),
    ActionSpec("codebook.policy_types", "create", GrantLevel.FULL),
    ActionSpec("codebook.policy_types", "update", GrantLevel.FULL),
    ActionSpec("codebook.policy_types", "import", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "list", GrantLevel.READ),
    ActionSpec("codebook.scenarios", "read", GrantLevel.READ),
    ActionSpec("codebook.scenarios", "export", GrantLevel.EXPORT),
    ActionSpec("codebook.scenarios", "create", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "update", GrantLevel.FULL),
    ActionSpec("codebook.scenarios", "import", GrantLevel.FULL),
    ActionSpec("codebook.area_codes", "list", GrantLevel.READ),
    ActionSpec("codebook.area_codes", "read", GrantLevel.READ),
    ActionSpec("codebook.area_codes", "export", GrantLevel.EXPORT),
    ActionSpec("codebook.area_codes", "resolve", GrantLevel.READ),
    ActionSpec("codebook.area_codes", "create", GrantLevel.FULL),
    ActionSpec("codebook.area_codes", "update", GrantLevel.FULL),
    ActionSpec("codebook.area_codes", "import", GrantLevel.FULL),
    ActionSpec("policy.sources", "list", GrantLevel.READ),
    ActionSpec("policy.sources", "read", GrantLevel.READ),
    ActionSpec("policy.sources", "export", GrantLevel.EXPORT),
    ActionSpec("policy.sources", "create", GrantLevel.FULL),
    ActionSpec("policy.sources", "update", GrantLevel.FULL),
    ActionSpec("policy.sources", "import", GrantLevel.FULL),
    ActionSpec("policy.sources", "purge", GrantLevel.FULL),
    ActionSpec("policy.crawler_monitoring", "list", GrantLevel.READ),
    ActionSpec("policy.crawler_monitoring", "export", GrantLevel.EXPORT),
    ActionSpec("policy.base_tags", "list", GrantLevel.READ),
    ActionSpec("policy.base_tags", "read", GrantLevel.READ),
    ActionSpec("policy.base_tags", "export", GrantLevel.EXPORT),
    ActionSpec("policy.base_tags", "create", GrantLevel.FULL),
    ActionSpec("policy.base_tags", "update", GrantLevel.FULL),
    ActionSpec("policy.base_tags", "import", GrantLevel.FULL),
    ActionSpec("policy.interpretations", "list", GrantLevel.READ),
    ActionSpec("policy.interpretations", "read", GrantLevel.READ),
    ActionSpec("policy.interpretations", "export", GrantLevel.EXPORT),
    ActionSpec("policy.interpretations", "create", GrantLevel.FULL),
    ActionSpec("policy.interpretations", "update", GrantLevel.FULL),
    ActionSpec("policy.interpretations", "import", GrantLevel.FULL),
    # 试发、批量运行和对话会调用大模型产生费用：试发和批量要「管理」档；多轮对话页本身就是对话，「仅查看」即可使用。
    ActionSpec("ai.prompts", "list", GrantLevel.READ),
    ActionSpec("ai.prompts", "export", GrantLevel.EXPORT),
    ActionSpec("ai.prompts", "create", GrantLevel.FULL),
    ActionSpec("ai.prompts", "update", GrantLevel.FULL),
    ActionSpec("ai.prompts", "delete", GrantLevel.FULL),
    ActionSpec("ai.prompts", "ask", GrantLevel.FULL),
    ActionSpec("ai.batch_runs", "list", GrantLevel.READ),
    ActionSpec("ai.batch_runs", "export", GrantLevel.EXPORT),
    ActionSpec("ai.batch_runs", "run", GrantLevel.FULL),
    ActionSpec("ai.batch_runs", "stop", GrantLevel.FULL),
    ActionSpec("ai.batch_runs", "delete", GrantLevel.FULL),
    ActionSpec("ai.chat", "chat", GrantLevel.READ),
)

MENU_SPECS: tuple[MenuSpec, ...] = (
    MenuSpec("menu.system", "系统管理", 10, icon="setting"),
    MenuSpec("menu.system.users", "用户管理", 11, "system-users", "system.users", "menu.system"),
    MenuSpec("menu.system.roles", "角色与权限", 12, "system-roles", "system.roles", "menu.system"),
    # 权限配置已并入「角色与权限」页；菜单停用，资源 system.permissions 仍用于授权判定。
    MenuSpec(
        "menu.system.permissions",
        "权限分配",
        13,
        "system-permissions",
        "system.permissions",
        "menu.system",
        enabled=False,
    ),
    MenuSpec("menu.system.scheduler", "任务调度", 15, "system-scheduler", "system.scheduler", "menu.system"),
    MenuSpec("menu.system.audit", "操作日志", 14, "system-audit", "system.audit", "menu.system"),
    MenuSpec("menu.policy", "政策", 20, enabled=True),
    MenuSpec("menu.policy.sources", "信源管理", 21, "policy-sources", "policy.sources", "menu.policy", enabled=True),
    MenuSpec(
        "menu.policy.crawler_monitoring",
        "爬虫监测",
        22,
        "policy-crawler-monitoring",
        "policy.crawler_monitoring",
        "menu.policy",
        enabled=True,
    ),
    MenuSpec(
        "menu.policy.interpretations",
        "政策解读列表",
        23,
        "policy-interpretations",
        "policy.interpretations",
        "menu.policy",
        enabled=True,
    ),
    MenuSpec(
        "menu.policy.base_tags",
        "政策基础标签表",
        24,
        "policy-base-tags",
        "policy.base_tags",
        "menu.policy",
        enabled=True,
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
        "行业场景码表",
        52,
        "codebook-scenarios",
        "codebook.scenarios",
        "menu.codebook",
        enabled=True,
    ),
    MenuSpec(
        "menu.codebook.area_codes",
        "省市区编码表",
        53,
        "codebook-area-codes",
        "codebook.area_codes",
        "menu.codebook",
        enabled=True,
    ),
    MenuSpec("menu.ai", "AI 打表", 60, enabled=True),
    MenuSpec("menu.ai.prompts", "提问配置", 61, "ai-prompts", "ai.prompts", "menu.ai", enabled=True),
    MenuSpec("menu.ai.batch_runs", "批量提问", 62, "ai-batch-runs", "ai.batch_runs", "menu.ai", enabled=True),
    MenuSpec("menu.ai.chat", "多轮对话", 63, "ai-chat", "ai.chat", "menu.ai", enabled=True),
)

SUPERADMIN_ROLE_CODE = "superadmin"
SUPERADMIN_ROLE_NAME = "超级管理员"
