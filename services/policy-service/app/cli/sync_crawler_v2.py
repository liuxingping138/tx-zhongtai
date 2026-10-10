"""爬虫监测 v2 同步的命令行入口，逻辑在 app.application.crawler_sync_v2。

用法见 app.application.crawler_sync_v2 模块说明。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime

from platform_common.clock import BEIJING

from app.application.crawler_sync_v2 import MODE_BACKFILL, MODE_INCREMENTAL, MODE_REPAIR, run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="爬虫监测 v2：按网站同步采集总表的统计")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backfill", action="store_true", help="从总表最早采集日回填到今天，并建立水位")
    group.add_argument("--days", type=int, default=None, help="修复：固定重算最近多少天，不动水位")
    parser.add_argument(
        "--since", type=date.fromisoformat, default=None, help="回填起始采集日（YYYY-MM-DD），默认取总表最早采集日"
    )
    parser.add_argument("--skip-existing", action="store_true", help="回填中断后续跑：跳过已入库的采集日")
    args = parser.parse_args()

    if args.days is not None and args.days < 1:
        parser.error("--days 必须大于 0")
    if (args.since or args.skip_existing) and not args.backfill:
        parser.error("--since / --skip-existing 只能配合 --backfill 使用")
    if args.since and args.since > datetime.now(BEIJING).date():
        parser.error("--since 不能晚于今天")

    mode = MODE_BACKFILL if args.backfill else MODE_REPAIR if args.days is not None else MODE_INCREMENTAL
    asyncio.run(run(mode=mode, days=args.days or 7, since=args.since, skip_existing=args.skip_existing))


if __name__ == "__main__":
    main()
