from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PromptTemplate


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
