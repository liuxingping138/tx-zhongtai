"""行业场景编码规则（按现有 8370 行数据反推，全部符合）。

- 行业编码 8 位 = 一级 2 位 + 二级 2 位 + 三级 2 位 + 00，新场景不新增行业，只查已有的。
- 场景编码 12 位 = 一级 3 位 + 二级 3 位 + 三级 3 位 + 000；某级为空记 000。
  每一级的号全局递增、不重复：已有的（同一上级路径下同名）沿用，新的一级取该级当前最大号 + 1。
- 行业场景编码 20 位 = 行业编码 + 场景编码。

码表里有一批通用场景只挂在一级行业下（二三级行业为空，如「医卫行业 → 视联网 > 千里眼」），AI 解读时
会按政策把行业填到三级。六级对不上时退一步按「一级行业 + 场景」找，编码用那一行的。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

EMPTY = "000"
LEVEL_MAX = 999
# 模型有时在新场景名称后面标「（新增）」，这种名称写进码表就永远留下了。
NEW_MARK = re.compile(r"[（(【\[]\s*新增\s*[）)】\]]")

Names = tuple[str, str, str]


@dataclass(frozen=True)
class ScenarioItem:
    industry: Names
    scenario: Names

    def key(self) -> tuple[Names, Names]:
        return self.industry, self.scenario


@dataclass(frozen=True)
class Codes:
    industry_code: str
    scenario_code: str

    @property
    def industry_scenario_code(self) -> str:
        return self.industry_code + self.scenario_code


# 一组行业场景名称和码表比对的结果（classify）：
EXISTS = "exists"  # 码表里已有，带编码
NEW = "new"  # 有一级场景路径码表里没有：new_level 是第一个查不到的那一级
ASSOCIATION = "association"  # 各级场景码表里都有，只是没挂在这个行业下
BAD_INDUSTRY = "bad_industry"  # 三级行业不在码表里：新场景不新增行业，只能改行
INVALID = "invalid"  # 一级场景为空，或有三级没二级，编不了码


@dataclass(frozen=True)
class Classification:
    kind: str
    new_level: int = 0
    codes: Codes | None = None


@dataclass
class CodeBook:
    industries: dict[Names, str] = field(default_factory=dict)
    levels: tuple[dict[tuple[str, ...], str], ...] = field(default_factory=lambda: ({}, {}, {}))
    maxima: list[int] = field(default_factory=lambda: [0, 0, 0])
    existing: dict[tuple[Names, Names], Codes] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[str, Names, str, Names]]) -> CodeBook:
        """rows：（行业编码，三级行业名，场景编码，三级场景名）。"""

        book = cls()
        for industry_code, industry, scenario_code, scenario in rows:
            if industry_code:
                book.industries.setdefault(industry, industry_code)
            if len(scenario_code) >= 9:  # noqa: PLR2004  场景编码前 9 位是三级各 3 位
                for level in range(3):
                    segment = scenario_code[level * 3 : level * 3 + 3]
                    if segment != EMPTY and scenario[level] and segment.isdigit():
                        book.levels[level].setdefault(scenario[: level + 1], segment)
                        book.maxima[level] = max(book.maxima[level], int(segment))
            if industry_code and scenario_code:
                book.existing.setdefault((industry, scenario), Codes(industry_code, scenario_code))
        return book

    def lookup(self, item: ScenarioItem) -> Codes | None:
        found = self.existing.get(item.key())
        if found or not (item.industry[1] or item.industry[2]):
            return found
        return self.existing.get(((item.industry[0], "", ""), item.scenario))

    def classify(self, item: ScenarioItem) -> Classification:
        """比对一组名称：码表已有、哪一级是新的、只是新挂一个行业，还是行业本身不在码表。只查不建。

        各级场景号按场景路径全局唯一、不分行业（见 _segment），所以「哪一级是新的」也只看场景路径。
        """

        found = self.lookup(item)
        if found:
            return Classification(EXISTS, codes=found)
        scenario = item.scenario
        if not scenario[0] or (not scenario[1] and scenario[2]):
            return Classification(INVALID)
        if item.industry not in self.industries:
            return Classification(BAD_INDUSTRY)
        for level in range(3):
            if scenario[level] and scenario[: level + 1] not in self.levels[level]:
                return Classification(NEW, new_level=level + 1)
        return Classification(ASSOCIATION)

    def _segment(self, level: int, path: tuple[str, ...]) -> str:
        if not path[-1]:
            return EMPTY
        known = self.levels[level].get(path)
        if known:
            return known
        if self.maxima[level] >= LEVEL_MAX:
            raise ValueError(f"第 {level + 1} 级场景编号已用到 {LEVEL_MAX}，编码规则放不下新的号")
        self.maxima[level] += 1
        segment = f"{self.maxima[level]:03d}"
        self.levels[level][path] = segment
        return segment

    def assign(self, item: ScenarioItem) -> tuple[Codes, bool]:
        """返回（编码，是否新建）。已有同名同路径的场景直接返回原编码，不重复建。"""

        found = self.lookup(item)
        if found:
            return found, False
        if any(NEW_MARK.search(name) for name in item.scenario):
            raise ValueError("场景名称里带「（新增）」这类标记，去掉后再同步")
        industry_code = self.industries.get(item.industry)
        if not industry_code:
            path = "/".join(name for name in item.industry if name)
            raise ValueError(f"行业「{path}」不在行业场景码表里，新场景不新增行业")
        if not item.scenario[0]:
            raise ValueError("一级场景为空，无法编码")
        if not item.scenario[1] and item.scenario[2]:
            raise ValueError("有三级场景却没有二级场景，无法编码")
        segments = [self._segment(level, item.scenario[: level + 1]) for level in range(3)]
        codes = Codes(industry_code, "".join(segments) + EMPTY)
        self.existing[item.key()] = codes
        return codes, True
