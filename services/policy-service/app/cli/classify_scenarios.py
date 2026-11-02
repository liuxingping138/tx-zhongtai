"""把还没和行业场景码表比对过的政策解读行比对完，新增场景归成候选。上线补数、码表服务恢复后补跑。

用法（policy-worker 里跑）：python -m app.cli.classify_scenarios
"""

from __future__ import annotations

import asyncio

from app.policy.application import scenario_engine


async def main() -> None:
    total = await scenario_engine.classify_backlog()
    print(f"已比对 {total} 行解读")


if __name__ == "__main__":
    asyncio.run(main())
