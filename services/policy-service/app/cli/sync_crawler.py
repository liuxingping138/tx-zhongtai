"""同步爬虫采集量（v1 任务口径）的命令行入口，逻辑在 app.application.crawler_sync。

用法见 app.application.crawler_sync 模块说明。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime

from platform_common.clock import BEIJING

from app.application.crawler_sync import run
from app.core.config import get_settings

settings = get_settings()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="同步爬虫采集量到政策库")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="强制回算最近多少天（跳过水位判断）。默认按入库时间水位决定重算哪些采集日",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help="从指定日期回填到今天（YYYY-MM-DD），优先于 --days。首次建议用爬虫库最早的采集日期，"
        "否则窗口外停更的任务会被算成「从未出数」。",
    )
    parser.add_argument("--tasks-only", action="store_true", help="只同步任务基线，不拉按天统计")
    parser.add_argument(
        "--fixed-window",
        action="store_true",
        help="不走入库时间水位，改为固定回算 --days 天（排查用）",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过库里已有的日期，用于长回填中途失败后续跑；当天和昨天仍会重算",
    )
    args = parser.parse_args()
    if args.since and args.since > datetime.now(BEIJING).date():
        parser.error("--since 不能晚于今天")
    if args.skip_existing and args.since is None and args.days is None and not args.fixed_window:
        parser.error("--skip-existing 只能配合人工固定区间使用")
    asyncio.run(
        run(
            days=max(args.days if args.days is not None else settings.crawler_sync_days, 1),
            tasks_only=args.tasks_only,
            since=args.since,
            skip_existing=args.skip_existing,
            use_watermark=args.days is None and not args.fixed_window,
        )
    )


if __name__ == "__main__":
    main()
