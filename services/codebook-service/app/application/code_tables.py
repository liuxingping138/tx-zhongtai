"""AI 模板引用的系统码表，输出成和「上传码表」一样的制表符文本（首行表头），模板里 @【上传码表】原样替换。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from platform_common.errors import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import code_tables as repo


@dataclass(frozen=True)
class CodeTable:
    title: str
    headers: tuple[str, ...]
    load: Callable[[AsyncSession], Awaitable[list[tuple[Any, ...]]]]


CODE_TABLES: dict[str, CodeTable] = {
    "policy_types": CodeTable("政策类型", ("政策类型名称", "政策类型定义", "优先级"), repo.policy_types),
    "scenarios": CodeTable(
        "行业场景（六级）", ("一级行业", "二级行业", "三级行业", "一级场景", "二级场景", "三级场景"), repo.scenarios
    ),
    "scenario_l1": CodeTable("行业场景（一级行业 + 一级场景）", ("一级行业", "一级场景"), repo.scenario_l1),
}


def _cell(value: Any) -> str:
    # 单元格里的换行和制表符会把一行拆成几行、几列，模型读到的就错位了。
    return " ".join(str(value or "").split())


async def render(session: AsyncSession, name: str) -> dict[str, Any]:
    table = CODE_TABLES.get(name)
    if table is None:
        raise NotFoundError(f"没有名为 {name} 的码表")
    rows = await table.load(session)
    lines = ["\t".join(table.headers), *("\t".join(_cell(value) for value in row) for row in rows)]
    return {"name": name, "title": table.title, "rows": len(rows), "text": "\n".join(lines)}
