"""导入旧打表系统的模板和批量历史。用法：python -m app.cli.import_legacy <导出目录> [--update] [--dry-run]

导出目录的结构和覆盖规则见 app.application.legacy_import。可以重复跑。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.application.legacy_import import import_legacy
from app.core.database import SessionLocal


async def main() -> None:
    parser = argparse.ArgumentParser(description="导入旧打表系统的模板和批量历史")
    parser.add_argument("root", type=Path, help="导出目录，含 legacy.json、prompt_files/、batch_runs/")
    parser.add_argument("--update", action="store_true", help="用旧库最新内容覆盖已导入、未在新系统里保存过的记录")
    parser.add_argument("--dry-run", action="store_true", help="只核对，不写库也不写数据卷")
    args = parser.parse_args()
    async with SessionLocal() as session:
        report = await import_legacy(session, args.root, write=not args.dry_run, update=args.update)
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()
    print(f"新增模板 {len(report.templates)} 个：{'、'.join(report.templates) or '无'}")
    print(f"新增批量任务 {len(report.runs)} 个")
    for line in report.updated:
        print(f"覆盖：{line}")
    for line in report.skipped:
        print(f"跳过：{line}")
    for line in report.warnings:
        print(f"注意：{line}")
    if args.dry_run:
        print("dry-run：没有提交")


if __name__ == "__main__":
    asyncio.run(main())
