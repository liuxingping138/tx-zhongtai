"""批量任务按天记账（ai_run_costs）。

任务上的费用是累计数：几天后点「重跑失败」、定时打标跨过零点，花的钱都加在同一条任务上。账单按北京日期算，
得知道每笔钱是哪天花的：执行进程每答完一行记进当天，写进度时把这段时间新增的按天加进流水表。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from platform_common.clock import BEIJING
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import billing as repo


@dataclass
class Spend:
    input_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    inference_cost: Decimal = Decimal(0)
    search_cost: Decimal = Decimal(0)
    # 放在最后：调用处按位置传前五个字段，加在中间会把费用错位。
    cached_tokens: int = 0

    def add(self, other: Spend) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_tokens += other.cached_tokens
        self.search_calls += other.search_calls
        self.inference_cost += other.inference_cost
        self.search_cost += other.search_cost


class Ledger:
    """还没写进流水表的花费，按北京日期分开。"""

    def __init__(self) -> None:
        self._unbooked: dict[date, Spend] = {}

    def add(self, when: datetime, spend: Spend) -> None:
        self._unbooked.setdefault(when.astimezone(BEIJING).date(), Spend()).add(spend)

    def take(self) -> dict[date, Spend]:
        """取走待记的部分。写库失败时用 restore 放回，下次接着记，钱不会丢也不会重复记。"""

        taken, self._unbooked = self._unbooked, {}
        return taken

    def restore(self, taken: dict[date, Spend]) -> None:
        for day, spend in taken.items():
            self._unbooked.setdefault(day, Spend()).add(spend)


async def book(session: AsyncSession, run_id: str, taken: dict[date, Spend]) -> None:
    rows = [
        {
            "run_id": run_id,
            "day": day,
            "input_tokens": spend.input_tokens,
            "output_tokens": spend.output_tokens,
            "cached_tokens": spend.cached_tokens,
            "search_calls": spend.search_calls,
            "inference_cost": spend.inference_cost,
            "search_cost": spend.search_cost,
        }
        for day, spend in taken.items()
    ]
    await repo.add_run_costs(session, rows)
