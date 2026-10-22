"""AI 模板引用的系统码表，模板里 @【上传码表】原样替换成这里给出的文本。

政策类型、一级行业 + 一级场景输出成和「上传码表」一样的制表符文本（首行表头）。六级行业场景按三级行业分组：
原样六列每行都重复一遍行业路径，3348 条路径约 10.6 万字，分组后行业只写一次，约 3.8 万字，包含的信息不变。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from platform_common.errors import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import code_tables as repo


@dataclass(frozen=True)
class CodeTable:
    title: str
    headers: tuple[str, ...]
    load: Callable[[AsyncSession], Awaitable[list[tuple[Any, ...]]]]
    # 把表头和行排成文本；不给就是制表符表格。
    layout: Callable[[tuple[str, ...], list[tuple[Any, ...]]], str] | None = field(default=None)


def _cell(value: Any) -> str:
    # 单元格里的换行和制表符会把一行拆成几行、几列，模型读到的就错位了。
    return " ".join(str(value or "").split())


def _tsv(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    return "\n".join(["\t".join(headers), *("\t".join(_cell(value) for value in row) for row in rows)])


# 层级之间的分隔。不用「/」：有场景名本身带斜杠（如「边坡/尾矿库监测」）。
LEVEL_SEP = " > "
SCENARIO_SEP = "；"
SCENARIO_GUIDE = (
    "行业场景码表：每行是一个三级行业，格式为「一级行业 > 二级行业 > 三级行业：场景；场景；…」。"
    "每个场景写成「一级场景 > 二级场景 > 三级场景」，不同场景用「；」分隔。"
    "行业和场景都是写到哪一级就是哪一级，没写的级别为空。"
)


def _path(values: tuple[Any, ...]) -> str:
    return LEVEL_SEP.join(text for text in (_cell(value) for value in values) if text)


def _grouped_scenarios(_headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    """六级码表按三级行业分组。行已按六级排好序，同一行业的场景挨在一起，保留一级、二级场景的上级行。"""

    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(_path(row[:3]), []).append(_path(row[3:]))
    lines = [f"{industry}：{SCENARIO_SEP.join(path for path in paths if path)}" for industry, paths in groups.items()]
    return "\n".join([SCENARIO_GUIDE, *lines])


CODE_TABLES: dict[str, CodeTable] = {
    "policy_types": CodeTable("政策类型", ("政策类型名称", "政策类型定义", "优先级"), repo.policy_types),
    "scenarios": CodeTable(
        "行业场景（六级）",
        ("一级行业", "二级行业", "三级行业", "一级场景", "二级场景", "三级场景"),
        repo.scenarios,
        _grouped_scenarios,
    ),
    "scenario_l1": CodeTable("行业场景（一级行业 + 一级场景）", ("一级行业", "一级场景"), repo.scenario_l1),
}


async def render(session: AsyncSession, name: str) -> dict[str, Any]:
    table = CODE_TABLES.get(name)
    if table is None:
        raise NotFoundError(f"没有名为 {name} 的码表")
    rows = await table.load(session)
    text = (table.layout or _tsv)(table.headers, rows)
    return {"name": name, "title": table.title, "rows": len(rows), "text": text}
