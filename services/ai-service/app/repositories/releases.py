from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import TemplateRelease


async def by_ids(session: AsyncSession, ids: Collection[str]) -> dict[str, TemplateRelease]:
    if not ids:
        return {}
    rows = await session.scalars(select(TemplateRelease).where(TemplateRelease.id.in_(list(ids))))
    return {row.id: row for row in rows}


async def list_for_prompt(session: AsyncSession, prompt_id: str) -> list[TemplateRelease]:
    rows = await session.scalars(
        select(TemplateRelease)
        .where(TemplateRelease.prompt_id == prompt_id)
        .order_by(TemplateRelease.release_no.desc())
    )
    return list(rows)


async def last_no(session: AsyncSession, prompt_id: str) -> int:
    value = await session.scalar(
        select(func.max(TemplateRelease.release_no)).where(TemplateRelease.prompt_id == prompt_id)
    )
    return int(value or 0)


def add(session: AsyncSession, release: TemplateRelease) -> None:
    session.add(release)
