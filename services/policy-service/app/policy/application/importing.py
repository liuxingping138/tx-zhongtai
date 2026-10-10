"""政策三张表 Excel 导入共用的步骤。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from platform_common.columns import ColumnSpec
from platform_common.excel import encode_skipped_file_async
from sqlalchemy.ext.asyncio import AsyncSession

# 每攒够这么多行 flush 一次，几万行的文件不会全堆到最后一次性写。
FLUSH_EVERY = 200
PASSED = "通过"


async def add_in_batches(session: AsyncSession, rows: Iterable[object]) -> int:
    count = 0
    for row in rows:
        session.add(row)
        count += 1
        if count % FLUSH_EVERY == 0:
            await session.flush()
    await session.flush()
    return count


def missing_area_reason(carried_reason: str) -> str:
    """省市区编码为空时的退回原因。

    文件若经过「省市区编码匹配」，校验说明列里已有「区县不标准」这类具体原因，比笼统的「为空」好排查，优先沿用。
    """

    if carried_reason and carried_reason != PASSED:
        return carried_reason
    return "省市区编码为空"


async def rejected_result(
    columns: tuple[ColumnSpec, ...], marked: list[dict[str, str]], *, blocked: int
) -> dict[str, Any]:
    """整批退回：一行都不写，把每行的校验说明标回原文件，用户改完整份重传。"""

    return {
        "inserted": 0,
        "updated": 0,
        "skipped": blocked,
        "total": len(marked),
        "rejected": True,
        "skipped_file": await encode_skipped_file_async(columns, marked),
    }


def inserted_result(inserted: int) -> dict[str, Any]:
    return {"inserted": inserted, "updated": 0, "skipped": 0, "total": inserted, "skipped_file": None}


def mark(values: dict[str, str], reasons: list[str]) -> dict[str, str]:
    return {**values, "skip_reason": "；".join(reasons) if reasons else PASSED}
