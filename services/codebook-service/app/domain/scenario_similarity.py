"""新增场景审核要用的码表上下文：同一上级下已有哪些场景、字面上最像的已有场景。

AI 新写的说法要不要进码表，人判断时最需要两样东西：它要挂的位置下面已经有什么，以及码表里有没有
换个说法的同一个场景。字面相似只能找出「县域医共体信息平台 ↔ 县域医共体」这类，意思近但字面不像的
（「智慧机场工程建设管理 ↔ 智慧航站楼」）靠人看同级场景判断，所以两样都给。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from platform_common.similarity import MEDIUM, similarity, similarity_level

Path = tuple[str, ...]

SIMILAR_LIMIT = 5
CROSS_INDUSTRY_CAP = 0.59  # 低于 HIGH
DESC_CHARS = 80


@dataclass
class _Node:
    desc: str = ""
    industries: set[str] = field(default_factory=set)
    industry_l1: set[str] = field(default_factory=set)


@dataclass
class ScenarioNodes:
    """码表里的场景节点（一级、一级>二级、一级>二级>三级），按场景路径去重，不分行业。"""

    nodes: dict[Path, _Node] = field(default_factory=dict)
    children: dict[Path, set[str]] = field(default_factory=dict)
    # 一级场景按一级行业分：新的一级场景要和同一个一级行业下已有的一级场景比。
    roots: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[tuple[str, str, str], Path, Path, str]]) -> ScenarioNodes:
        """rows：（三级行业名，三级场景名，三级场景描述，90 字场景描述）。"""

        book = cls()
        for industry, scenario, descs, desc_90 in rows:
            industry_path = "/".join(name for name in industry if name)
            depth = sum(1 for name in scenario if name)
            for level in range(depth):
                path = scenario[: level + 1]
                if not all(path):
                    break
                node = book.nodes.setdefault(path, _Node())
                node.industries.add(industry_path)
                node.industry_l1.add(industry[0])
                node.desc = node.desc or descs[level] or (desc_90 if level == depth - 1 else "")
                if level == 0:
                    book.roots.setdefault(industry[0], set()).add(path[0])
                else:
                    book.children.setdefault(path[:-1], set()).add(path[-1])
        return book

    def siblings(self, path: Path, industry_l1: Iterable[str]) -> list[dict[str, Any]]:
        """这个新场景要挂的位置下面，码表里已有的场景和各自的下级数。"""

        parent = path[:-1]
        if parent:
            names = self.children.get(parent, set())
        else:
            names = set().union(*(self.roots.get(name, set()) for name in industry_l1))
        return [{"name": name, "children": len(self.children.get((*parent, name), set()))} for name in sorted(names)]

    def _score(self, name: str, node_path: Path, industry_l1: set[str]) -> float:
        score = similarity(name, node_path[-1])
        # 不在这些一级行业下的已有场景，字面再像也多半不是一回事（「智慧机场工程建设管理」和工会的「工程建设管理」）：
        # 最多算「中」，照样列出来给人看，但不据此建议合并
        if industry_l1 and not (self.nodes[node_path].industry_l1 & industry_l1):
            score = min(score, CROSS_INDUSTRY_CAP)
        return score

    def similar(self, path: Path, industry_l1: Iterable[str] = (), limit: int = SIMILAR_LIMIT) -> list[dict[str, Any]]:
        """码表里字面上最像的已有场景（任意一级），只给相似度到「中」的。传了一级行业时，别的行业下的最多算「中」。"""

        name, industries = path[-1], {item for item in industry_l1 if item}
        scored = [
            (self._score(name, node_path, industries), node_path) for node_path in self.nodes if node_path != path
        ]
        best = sorted((item for item in scored if item[0] >= MEDIUM), key=lambda item: (-item[0], item[1]))
        return [
            {
                "path": list(node_path),
                "score": score,
                "level": similarity_level(score),
                "desc": self.nodes[node_path].desc[:DESC_CHARS],
                "industry": "、".join(sorted(self.nodes[node_path].industry_l1)[:3]),
            }
            for score, node_path in best[:limit]
        ]

    def paths_under(self, industry_l1: Iterable[str]) -> list[str]:
        """挂在这些一级行业下的全部场景路径（各级都列），给 AI 找相似场景当参照。"""

        wanted = {name for name in industry_l1 if name}
        return [" > ".join(path) for path in sorted(self.nodes) if self.nodes[path].industry_l1 & wanted]

    def industries_of(self, path: Path) -> list[str]:
        node = self.nodes.get(path)
        return sorted(node.industries) if node else []
