"""模板测试样本的逐行数据：试发可以选第几行发，发之前先看这一行要替换进提示词的值。"""

from __future__ import annotations

from typing import Any

import anyio
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import run_excel_parse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.prompts import require
from app.application.sheets import read_sheet
from app.core import storage
from app.domain.categories import CategoryAccess
from app.domain.models import PromptTemplate

# 试发的下拉最多列这么多行；每格只给开头一段和总字数，几百行带正文的样本也不会一次传几兆。
ROWS_MAX = 100
CELL_MAX = 200


async def _read(template: PromptTemplate, limit: int) -> tuple[list[str], list[dict[str, str]]]:
    excel = anyio.Path(storage.prompt_file(template.id, "excel"))
    if not template.excel_name or not await excel.is_file():
        return [], []
    return await run_excel_parse(lambda content: read_sheet(content, limit=limit), await excel.read_bytes())


async def row_values(template: PromptTemplate, row: int) -> dict[str, str]:
    """测试样本第 row 条数据（从 0 数）的完整值；没有测试样本时为空，变量原样发出。"""

    _, rows = await _read(template, row + 1)
    if not rows:
        return {}
    if row >= len(rows):
        raise ApiError(
            f"测试样本只有 {len(rows)} 行，没有第 {row + 1} 行", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    return rows[row]


async def preview(session: AsyncSession, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    template = await require(session, prompt_id)
    access.require_read(template.category)
    headers, rows = await _read(template, ROWS_MAX)
    return {
        "headers": headers,
        "total": template.excel_rows if headers else 0,
        "rows": [
            {
                "row": index + 1,
                "values": {name: (values.get(name) or "")[:CELL_MAX] for name in headers},
                "lengths": {name: len(values.get(name) or "") for name in headers},
            }
            for index, values in enumerate(rows)
        ],
    }
