"""导入省市区编码种子。用法：uv run python -m app.cli.seed_area_codes"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.application.actors import Actor
from app.application.area_codes import upsert_area_code_rows
from app.application.area_sql import parse_area_sql
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codebook.cli.seed_area_codes")

_SQL_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "data" / "cfg_all_area_code_info.sql",
    Path(__file__).resolve().parents[4] / "docs" / "configuration_cfg_all_area_code_info.sql",
)


def _sql_path() -> Path:
    for path in _SQL_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("未找到省市区编码 SQL：cfg_all_area_code_info.sql")


async def main() -> None:
    path = _sql_path()
    rows = parse_area_sql(path.read_text(encoding="utf-8"))
    actor = Actor(id="system", name="系统导入")
    async with SessionLocal() as session:
        stats = await upsert_area_code_rows(
            session,
            actor,
            rows,
            event_type="codebook.area_code.imported",
        )
        await session.commit()
    logger.info(
        "area_codes_seeded source=%s inserted=%s skipped=%s total=%s",
        path,
        stats["inserted"],
        stats["skipped"],
        stats["total"],
    )


if __name__ == "__main__":
    asyncio.run(main())
