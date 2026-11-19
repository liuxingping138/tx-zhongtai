"""知识库权限范围（按文件类型、行业类型划分）与标准枚举。"""

from __future__ import annotations

from dataclasses import dataclass

from platform_common.errors import PermissionDeniedError

# 文件类型：slug -> 中文名（与 IAM catalog thinktank.file_type.<slug> 一一对应）
FILE_TYPE_ITEMS: tuple[tuple[str, str], ...] = (
    ("product", "产品"),
    ("jingfen", "经分"),
    ("industry_guide", "行业营销指引"),
    ("notice", "通知"),
    ("bulletin", "通报"),
    ("work_meeting", "工作会"),
    ("deployment", "工作部署&专项行动"),
    ("network_plan", "网络规划"),
    ("assessment", "考核"),
    ("gov_reform", "政企改革&数字化"),
    ("customer_view", "客户视图"),
    ("channel_eco", "渠道&生态"),
    ("intl_biz", "国际业务"),
    ("project_dept", "项目部"),
    ("other", "其他"),
    ("undefined", "未定义"),
)

# 行业类型：slug -> 中文名（与 IAM catalog thinktank.industry_type.<slug> 一一对应）
INDUSTRY_TYPE_ITEMS: tuple[tuple[str, str], ...] = (
    ("sme", "中小"),
    ("gov", "党政"),
    ("energy", "工业能源"),
    ("edu", "教育"),
    ("health", "医卫"),
    ("transport", "交通物流"),
    ("it", "IT互联网"),
    ("finance", "金融"),
    ("agri", "农业"),
    ("housing", "住建"),
    ("culture", "文旅"),
    ("none", "无"),
)

FILE_TYPES: tuple[str, ...] = tuple(label for slug, label in FILE_TYPE_ITEMS if slug != "undefined")
INDUSTRY_TYPES: tuple[str, ...] = tuple(label for _, label in INDUSTRY_TYPE_ITEMS)
OPERATOR_TYPES: tuple[str, ...] = ("未知", "电信", "联通", "移动")
PRODUCT_TYPES: tuple[str, ...] = (
    "量子",
    "解决方案",
    "云",
    "网",
    "数",
    "智",
    "安",
    "语音",
    "消息",
    "ICT",
    "数字平台",
    "服务",
    "无",
)
MARKET_CATEGORIES: tuple[str, ...] = ("行客", "商客", "综合", "无")
PROVINCES: tuple[str, ...] = (
    "集团",
    "北京市",
    "天津市",
    "河北省",
    "山西省",
    "内蒙古自治区",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "上海市",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "广西壮族自治区",
    "海南省",
    "重庆市",
    "四川省",
    "贵州省",
    "云南省",
    "西藏自治区",
    "陕西省",
    "甘肃省",
    "青海省",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
)

FILE_TYPE_RESOURCE_BY_VALUE: dict[str, str] = {
    ("" if slug == "undefined" else label): f"thinktank.file_type.{slug}" for slug, label in FILE_TYPE_ITEMS
}
INDUSTRY_RESOURCE_BY_VALUE: dict[str, str] = {
    label: f"thinktank.industry_type.{slug}" for slug, label in INDUSTRY_TYPE_ITEMS
}
ALL_SCOPE_RESOURCES: list[str] = [
    *FILE_TYPE_RESOURCE_BY_VALUE.values(),
    *INDUSTRY_RESOURCE_BY_VALUE.values(),
]

_LEVEL_RANK: dict[str, int] = {"NONE": 0, "READ": 1, "EXPORT": 2, "FULL": 3}
_EXPORT_LEVELS = frozenset({"EXPORT", "FULL"})
_EDIT_LEVELS = frozenset({"FULL"})


def _cap_level(level: str, cap: str | None) -> str:
    if not cap or cap not in _LEVEL_RANK:
        return level
    return cap if _LEVEL_RANK.get(level, 0) > _LEVEL_RANK[cap] else level


def split_multi_tags(raw: str | None) -> list[str]:
    """拆分竖线分隔的标签，例如 `中小|教育` -> `['中小', '教育']`。"""

    text = (raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def effective_industry_tags(raw: str | None) -> list[str]:
    """记录的行业归属为空时视为「无」（未划分行业/通用）。"""

    parts = split_multi_tags(raw)
    return parts or ["无"]


def normalize_file_type_input(raw: str | None) -> str:
    """前端或导入传入「未定义」或空串统一规范为存储值空串。"""

    val = (raw or "").strip()
    if val in {"", "未定义"}:
        return ""
    return val


@dataclass(frozen=True)
class KnowledgeAccess:
    """当前用户在文件类型与行业类型上的权限范围。按 IAM 资源档位算出，一次请求内不变。"""

    file_type_levels: dict[str, str]
    industry_levels: dict[str, str]

    @classmethod
    def from_levels(cls, levels: dict[str, str], *, module_level: str | None = None) -> KnowledgeAccess:
        file_levels = {
            value: _cap_level(levels[res], module_level)
            for value, res in FILE_TYPE_RESOURCE_BY_VALUE.items()
            if res in levels and _cap_level(levels[res], module_level) != "NONE"
        }
        ind_levels = {
            value: _cap_level(levels[res], module_level)
            for value, res in INDUSTRY_RESOURCE_BY_VALUE.items()
            if res in levels and _cap_level(levels[res], module_level) != "NONE"
        }
        return cls(file_type_levels=file_levels, industry_levels=ind_levels)

    @property
    def readable_file_types(self) -> frozenset[str]:
        return frozenset(self.file_type_levels)

    @property
    def exportable_file_types(self) -> frozenset[str]:
        return frozenset(k for k, lvl in self.file_type_levels.items() if lvl in _EXPORT_LEVELS)

    @property
    def editable_file_types(self) -> frozenset[str]:
        return frozenset(k for k, lvl in self.file_type_levels.items() if lvl in _EDIT_LEVELS)

    @property
    def readable_industries(self) -> frozenset[str]:
        return frozenset(self.industry_levels)

    @property
    def exportable_industries(self) -> frozenset[str]:
        return frozenset(k for k, lvl in self.industry_levels.items() if lvl in _EXPORT_LEVELS)

    @property
    def editable_industries(self) -> frozenset[str]:
        return frozenset(k for k, lvl in self.industry_levels.items() if lvl in _EDIT_LEVELS)

    def _matches(
        self,
        file_type: str,
        industry_type: str,
        allowed_ft: frozenset[str],
        allowed_ind: frozenset[str],
        *,
        require_all_industries: bool = False,
    ) -> bool:
        ft = normalize_file_type_input(file_type)
        if ft not in allowed_ft:
            return False
        industries = effective_industry_tags(industry_type)
        if require_all_industries:
            return all(item in allowed_ind for item in industries)
        return any(item in allowed_ind for item in industries)

    def can_read_record(self, file_type: str, industry_type: str) -> bool:
        return self._matches(file_type, industry_type, self.readable_file_types, self.readable_industries)

    def can_export_record(self, file_type: str, industry_type: str) -> bool:
        return self._matches(file_type, industry_type, self.exportable_file_types, self.exportable_industries)

    def can_edit_record(self, file_type: str, industry_type: str) -> bool:
        return self._matches(
            file_type,
            industry_type,
            self.editable_file_types,
            self.editable_industries,
            require_all_industries=True,
        )

    def require_read(self, file_type: str, industry_type: str) -> None:
        if not self.can_read_record(file_type, industry_type):
            ft_label = file_type or "未定义"
            ind_label = industry_type or "无"
            raise PermissionDeniedError(f"没有「{ft_label} / {ind_label}」范围的查看权限")

    def require_export(self, file_type: str, industry_type: str) -> None:
        if not self.can_export_record(file_type, industry_type):
            ft_label = file_type or "未定义"
            ind_label = industry_type or "无"
            raise PermissionDeniedError(f"没有「{ft_label} / {ind_label}」范围的下载或导出权限")

    def require_edit(self, file_type: str, industry_type: str) -> None:
        if not self.can_edit_record(file_type, industry_type):
            ft_label = file_type or "未定义"
            ind_label = industry_type or "无"
            raise PermissionDeniedError(f"没有「{ft_label} / {ind_label}」范围的管理编辑权限")

    def to_summary(self) -> dict[str, object]:
        return {
            "readable_file_types": [
                label
                for _, label in FILE_TYPE_ITEMS
                if ("" if label == "未定义" else label) in self.readable_file_types
            ],
            "exportable_file_types": [
                label
                for _, label in FILE_TYPE_ITEMS
                if ("" if label == "未定义" else label) in self.exportable_file_types
            ],
            "editable_file_types": [
                label
                for _, label in FILE_TYPE_ITEMS
                if ("" if label == "未定义" else label) in self.editable_file_types
            ],
            "readable_industries": [label for label in INDUSTRY_TYPES if label in self.readable_industries],
            "exportable_industries": [label for label in INDUSTRY_TYPES if label in self.exportable_industries],
            "editable_industries": [label for label in INDUSTRY_TYPES if label in self.editable_industries],
        }


FULL_ACCESS = KnowledgeAccess(
    file_type_levels=dict.fromkeys(FILE_TYPE_RESOURCE_BY_VALUE, "FULL"),
    industry_levels=dict.fromkeys(INDUSTRY_RESOURCE_BY_VALUE, "FULL"),
)
