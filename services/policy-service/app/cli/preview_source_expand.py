"""信源按栏目展开的预览，逻辑在 app.crawlconfig.application.expand_preview。

在 policy-worker 容器里跑（它能连爬虫库），只读、不改库：
  python -m app.cli.preview_source_expand --from 2026-10-26 --out /tmp/expand.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from app.crawlconfig.application.expand_preview import preview


def main() -> None:
    parser = argparse.ArgumentParser(description="信源按栏目展开的预览：写成 Excel，不改库")
    parser.add_argument("--from", dest="expand_from", type=date.fromisoformat, required=True, help="从这天起建的规则")
    parser.add_argument("--out", type=Path, required=True, help="Excel 输出路径")
    args = parser.parse_args()
    content, summary = asyncio.run(preview(args.expand_from))
    args.out.write_bytes(content)
    print("，".join(f"{name} {count}" for name, count in summary.items()))


if __name__ == "__main__":
    main()
