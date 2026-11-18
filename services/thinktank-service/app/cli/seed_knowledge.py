"""导入知识库历史资料、操作日志与收藏数据。用法：uv run python -m app.cli.seed_knowledge [--force] [--user-map JSON]"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.core.database import SessionLocal
from app.knowledge.application.seed_data import ensure_seed_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thinktank.cli.seed_knowledge")


async def main(*, force: bool = False, user_map: dict[str, str] | None = None) -> dict[str, int]:
    async with SessionLocal() as session:
        stats = await ensure_seed_data(session, force=force, user_map=user_map)
        await session.commit()
    logger.info(
        "knowledge_seeded files=%s logs=%s favorites=%s force=%s",
        stats["files"],
        stats["logs"],
        stats["favorites"],
        force,
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化或增量补齐知识库数据（含历史操作日志和收藏）")
    parser.add_argument("--force", action="store_true", help="即使已有数据也按主键补齐缺失的资料、日志和收藏")
    parser.add_argument(
        "--user-map",
        default="",
        help='可选：JSON 映射原账号到新 IAM user_id，如 \'{"superAdmin":"<uuid>"}\'',
    )
    args = parser.parse_args()
    parsed_map = json.loads(args.user_map) if args.user_map else None
    asyncio.run(main(force=args.force, user_map=parsed_map))
