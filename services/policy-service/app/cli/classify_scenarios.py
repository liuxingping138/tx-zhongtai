"""把还没和行业场景码表比对过的政策解读行比对完，新增场景归成候选。上线补数、码表服务恢复后补跑。

用法（policy-worker 里跑）：python -m app.cli.classify_scenarios [--resimilar]
  --resimilar  顺带给待审的新增场景重算「最像的已有场景」（相似度口径改了、码表里新加了一批场景之后）
"""

from __future__ import annotations

import asyncio
import sys

from app.policy.application import scenario_engine


async def main() -> None:
    total = await scenario_engine.classify_backlog()
    print(f"已比对 {total} 行解读")
    if "--resimilar" in sys.argv[1:]:
        print(f"已重算 {await scenario_engine.refresh_pending_similar()} 个待审场景的相似场景")


if __name__ == "__main__":
    asyncio.run(main())
