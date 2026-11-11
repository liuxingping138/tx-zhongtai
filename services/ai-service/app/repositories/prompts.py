from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import BatchRun, PromptTemplate


async def list_all(session: AsyncSession, *, categories: Collection[str]) -> list[PromptTemplate]:
    result = await session.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.category.in_(list(categories)))
        .order_by(PromptTemplate.updated_at.desc())
    )
    return list(result)


async def list_online(session: AsyncSession, *, category: str) -> list[PromptTemplate]:
    result = await session.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.category == category, PromptTemplate.release_id.is_not(None))
        .order_by(PromptTemplate.title)
    )
    return list(result)


async def get(session: AsyncSession, prompt_id: str, *, lock: bool = False) -> PromptTemplate | None:
    statement = select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


def add(session: AsyncSession, template: PromptTemplate) -> None:
    session.add(template)


async def delete(session: AsyncSession, template: PromptTemplate) -> None:
    await session.delete(template)


async def categories_by_ids(session: AsyncSession, ids: Collection[str]) -> dict[str, str]:
    """操作日志补「类型」：审计事件的目标是模板ID或任务ID，各查出模板类型。
    模板删了的，按它留下的任务（删任务只是软删）取发起时快照的类型。"""

    wanted = list(ids)
    found: dict[str, str] = {}
    for row in await session.execute(
        select(BatchRun.prompt_id, BatchRun.prompt_category).where(BatchRun.prompt_id.in_(wanted))
    ):
        found[row.prompt_id] = row.prompt_category
    for row in await session.execute(select(BatchRun.id, BatchRun.prompt_category).where(BatchRun.id.in_(wanted))):
        found[row.id] = row.prompt_category
    # 现存模板以当前类型为准，覆盖上面按任务取的。
    for row in await session.execute(
        select(PromptTemplate.id, PromptTemplate.category).where(PromptTemplate.id.in_(wanted))
    ):
        found[row.id] = row.category
    return found
