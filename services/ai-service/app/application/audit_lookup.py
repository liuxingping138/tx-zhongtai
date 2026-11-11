"""操作日志补「类型」：按审计事件的目标（模板ID或任务ID）查模板类型。见 api/audit_lookup。"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import prompts as repo

ID_MAX_CHARS = 64  # 审计事件 target_id 的列宽


async def categories(session: AsyncSession, ids: Collection[str]) -> dict[str, str]:
    wanted = {item for item in ids if 0 < len(item) <= ID_MAX_CHARS}
    return await repo.categories_by_ids(session, wanted) if wanted else {}
