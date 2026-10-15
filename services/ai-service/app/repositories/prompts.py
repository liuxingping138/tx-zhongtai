from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PromptTemplate


async def list_all(session: AsyncSession) -> list[PromptTemplate]:
    result = await session.scalars(select(PromptTemplate).order_by(PromptTemplate.updated_at.desc()))
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
