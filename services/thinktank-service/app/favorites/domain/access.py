"""我的收藏实时跨子库权限视图：资料库按二维范围过滤，报告库/方案库按资源档位判断。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.knowledge.domain.scopes import ALL_SCOPE_RESOURCES, KNOWLEDGE_DOWNLOAD_RESOURCE, KnowledgeAccess

_READ_LEVELS = frozenset({"READ", "EXPORT", "FULL"})
_EXPORT_LEVELS = frozenset({"EXPORT", "FULL"})

LIBRARY_LABELS: dict[str, str] = {
    "knowledge": "资料库",
    "reports": "报告库",
    "proposals": "方案库",
}

ALL_FAVORITES_SCOPE_RESOURCES: list[str] = [
    "thinktank.knowledge",
    "thinktank.reports",
    "thinktank.proposals",
    KNOWLEDGE_DOWNLOAD_RESOURCE,
    "thinktank.reports.download",
    "thinktank.proposals.download",
    *ALL_SCOPE_RESOURCES,
]


@dataclass(frozen=True)
class FavoritesAccess:
    """当前用户在智库三个子库上的实时访问、下载与导出能力。"""

    knowledge: KnowledgeAccess | None = None
    reports_level: str | None = None
    proposals_level: str | None = None
    reports_allow_download: bool = False
    proposals_allow_download: bool = False

    @classmethod
    def from_levels(cls, levels: Mapping[str, str]) -> FavoritesAccess:
        k_level = levels.get("thinktank.knowledge")
        knowledge = KnowledgeAccess.from_levels(dict(levels), module_level=k_level) if k_level in _READ_LEVELS else None
        r_level = levels.get("thinktank.reports")
        p_level = levels.get("thinktank.proposals")
        return cls(
            knowledge=knowledge,
            reports_level=r_level if r_level in _READ_LEVELS else None,
            proposals_level=p_level if p_level in _READ_LEVELS else None,
            reports_allow_download=levels.get("thinktank.reports.download") in _READ_LEVELS,
            proposals_allow_download=levels.get("thinktank.proposals.download") in _READ_LEVELS,
        )

    @property
    def can_read_knowledge(self) -> bool:
        return (
            self.knowledge is not None
            and bool(self.knowledge.readable_file_types)
            and bool(self.knowledge.readable_industries)
        )

    @property
    def can_read_reports(self) -> bool:
        return self.reports_level in _READ_LEVELS

    @property
    def can_read_proposals(self) -> bool:
        return self.proposals_level in _READ_LEVELS

    @property
    def reports_can_download(self) -> bool:
        return self.can_read_reports and self.reports_allow_download

    @property
    def proposals_can_download(self) -> bool:
        return self.can_read_proposals and self.proposals_allow_download

    @property
    def reports_can_export(self) -> bool:
        return self.reports_level in _EXPORT_LEVELS

    @property
    def proposals_can_export(self) -> bool:
        return self.proposals_level in _EXPORT_LEVELS


@dataclass(frozen=True)
class FavoritesQuery:
    library: str = "all"
    keyword: str | None = None
    page: int = 1
    page_size: int = 20
