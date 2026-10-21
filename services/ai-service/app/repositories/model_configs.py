from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AiModel


async def list_all(session: AsyncSession, *, enabled_only: bool = False) -> list[AiModel]:
    statement = select(AiModel).order_by(AiModel.sort_order, AiModel.id)
    if enabled_only:
        statement = statement.where(AiModel.enabled.is_(True))
    return list(await session.scalars(statement))


async def get(session: AsyncSession, model_id: str, *, lock: bool = False) -> AiModel | None:
    statement = select(AiModel).where(AiModel.id == model_id)
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


def add(session: AsyncSession, row: AiModel) -> None:
    session.add(row)
