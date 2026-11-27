"""智库微服务的资源、动作与菜单目录。"""

from __future__ import annotations

from app.domain.catalog_types import ActionSpec, MenuSpec, ResourceSpec
from app.domain.enums import GrantLevel, NodeType

THINKTANK_FAVORITES_CODE = "thinktank.favorites"
THINKTANK_LIBRARY_CODES: tuple[str, ...] = (
    "thinktank.knowledge",
    "thinktank.reports",
    "thinktank.proposals",
)

# 文件类型范围资源：编码后缀与 thinktank-service domain/knowledge_scopes.py 一一对应。
FILE_TYPE_SCOPES: tuple[tuple[str, str], ...] = (
    ("product", "文件类型：产品"),
    ("jingfen", "文件类型：经分"),
    ("industry_guide", "文件类型：行业营销指引"),
    ("notice", "文件类型：通知"),
    ("bulletin", "文件类型：通报"),
    ("work_meeting", "文件类型：工作会"),
    ("deployment", "文件类型：工作部署&专项行动"),
    ("network_plan", "文件类型：网络规划"),
    ("assessment", "文件类型：考核"),
    ("gov_reform", "文件类型：政企改革&数字化"),
    ("customer_view", "文件类型：客户视图"),
    ("channel_eco", "文件类型：渠道&生态"),
    ("intl_biz", "文件类型：国际业务"),
    ("project_dept", "文件类型：项目部"),
    ("other", "文件类型：其他"),
    ("undefined", "文件类型：未定义"),
)

# 行业类型范围资源：编码后缀与 thinktank-service domain/knowledge_scopes.py 一一对应。
INDUSTRY_TYPE_SCOPES: tuple[tuple[str, str], ...] = (
    ("sme", "行业类型：中小"),
    ("gov", "行业类型：党政"),
    ("energy", "行业类型：工业能源"),
    ("edu", "行业类型：教育"),
    ("health", "行业类型：医卫"),
    ("transport", "行业类型：交通物流"),
    ("it", "行业类型：IT互联网"),
    ("finance", "行业类型：金融"),
    ("agri", "行业类型：农业"),
    ("housing", "行业类型：住建"),
    ("culture", "行业类型：文旅"),
    ("none", "行业类型：无"),
)


def _library_actions(resource_code: str) -> tuple[ActionSpec, ...]:
    return (
        ActionSpec(resource_code, "list", GrantLevel.READ),
        ActionSpec(resource_code, "read", GrantLevel.READ),
        ActionSpec(resource_code, "preview", GrantLevel.READ),
        ActionSpec(resource_code, "favorite", GrantLevel.READ),
        ActionSpec(resource_code, "export", GrantLevel.EXPORT),
        ActionSpec(resource_code, "export_undefined", GrantLevel.EXPORT),
        ActionSpec(resource_code, "download", GrantLevel.EXPORT),
        ActionSpec(resource_code, "create", GrantLevel.FULL),
        ActionSpec(resource_code, "update", GrantLevel.FULL),
        ActionSpec(resource_code, "upload_tags", GrantLevel.FULL),
        ActionSpec(resource_code, "delete", GrantLevel.FULL),
    )


def _scope_actions(resource_code: str) -> tuple[ActionSpec, ...]:
    return (
        ActionSpec(resource_code, "list", GrantLevel.READ),
        ActionSpec(resource_code, "export", GrantLevel.EXPORT),
        ActionSpec(resource_code, "update", GrantLevel.FULL),
    )


THINKTANK_SCOPE_PREFIXES: tuple[str, ...] = ("thinktank.file_type.", "thinktank.industry_type.")

THINKTANK_RESOURCE_SPECS: tuple[ResourceSpec, ...] = (
    ResourceSpec("thinktank", "智库", "thinktank-service", NodeType.DIRECTORY, True, 45),
    ResourceSpec("thinktank.knowledge", "资料库", "thinktank-service", NodeType.RESOURCE, True, 451, "thinktank"),
    ResourceSpec("thinktank.reports", "报告库", "thinktank-service", NodeType.RESOURCE, True, 452, "thinktank"),
    ResourceSpec("thinktank.proposals", "方案库", "thinktank-service", NodeType.RESOURCE, True, 453, "thinktank"),
    ResourceSpec("thinktank.favorites", "我的收藏", "thinktank-service", NodeType.RESOURCE, True, 454, "thinktank"),
    ResourceSpec(
        "thinktank.knowledge.file_type",
        "文件类型范围",
        "thinktank-service",
        NodeType.DIRECTORY,
        True,
        458,
        "thinktank.knowledge",
    ),
    ResourceSpec(
        "thinktank.knowledge.industry_type",
        "行业类型范围",
        "thinktank-service",
        NodeType.DIRECTORY,
        True,
        459,
        "thinktank.knowledge",
    ),
    *(
        ResourceSpec(
            f"thinktank.file_type.{slug}",
            name,
            "thinktank-service",
            NodeType.RESOURCE,
            True,
            460 + idx,
            "thinktank.knowledge.file_type",
        )
        for idx, (slug, name) in enumerate(FILE_TYPE_SCOPES)
    ),
    *(
        ResourceSpec(
            f"thinktank.industry_type.{slug}",
            name,
            "thinktank-service",
            NodeType.RESOURCE,
            True,
            480 + idx,
            "thinktank.knowledge.industry_type",
        )
        for idx, (slug, name) in enumerate(INDUSTRY_TYPE_SCOPES)
    ),
)

THINKTANK_ACTION_SPECS: tuple[ActionSpec, ...] = (
    *_library_actions("thinktank.knowledge"),
    *_library_actions("thinktank.reports"),
    *_library_actions("thinktank.proposals"),
    ActionSpec("thinktank.favorites", "list", GrantLevel.READ),
    ActionSpec("thinktank.favorites", "favorite", GrantLevel.READ),
    *(action for slug, _ in FILE_TYPE_SCOPES for action in _scope_actions(f"thinktank.file_type.{slug}")),
    *(action for slug, _ in INDUSTRY_TYPE_SCOPES for action in _scope_actions(f"thinktank.industry_type.{slug}")),
)

THINKTANK_MENU_SPECS: tuple[MenuSpec, ...] = (
    MenuSpec("menu.thinktank", "智库", 45, enabled=True),
    MenuSpec(
        "menu.thinktank.knowledge",
        "资料库",
        451,
        "thinktank-knowledge",
        "thinktank.knowledge",
        "menu.thinktank",
        enabled=True,
    ),
    MenuSpec(
        "menu.thinktank.reports",
        "报告库",
        452,
        "thinktank-reports",
        "thinktank.reports",
        "menu.thinktank",
        enabled=True,
    ),
    MenuSpec(
        "menu.thinktank.proposals",
        "方案库",
        453,
        "thinktank-proposals",
        "thinktank.proposals",
        "menu.thinktank",
        enabled=True,
    ),
    MenuSpec(
        "menu.thinktank.favorites",
        "我的收藏",
        454,
        "thinktank-favorites",
        "thinktank.favorites",
        "menu.thinktank",
        enabled=True,
    ),
)
