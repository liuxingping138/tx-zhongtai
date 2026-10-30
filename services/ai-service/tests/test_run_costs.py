"""批量任务按天记账：重跑、跨零点的钱记到实际花钱那天。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.run_costs import Ledger, Spend


def test_spend_is_split_by_beijing_day_and_restored_when_booking_fails() -> None:
    ledger = Ledger()
    ledger.add(datetime(2026, 10, 21, 15, 59, tzinfo=UTC), Spend(10, 1, 0, Decimal("0.1"), Decimal(0)))  # 北京 23:59
    ledger.add(datetime(2026, 10, 21, 16, 1, tzinfo=UTC), Spend(20, 2, 1, Decimal("0.2"), Decimal("0.004")))  # 次日
    taken = ledger.take()
    assert {day: spend.input_tokens for day, spend in taken.items()} == {date(2026, 10, 21): 10, date(2026, 10, 22): 20}
    assert ledger.take() == {}
    # 写库失败放回去；期间又答完的一行并进同一天，下次一起记。
    ledger.add(datetime(2026, 10, 22, 1, 0, tzinfo=UTC), Spend(5, 0, 0, Decimal("0.05"), Decimal(0)))
    ledger.restore(taken)
    again = ledger.take()
    assert again[date(2026, 10, 22)] == Spend(25, 2, 1, Decimal("0.25"), Decimal("0.004"))
    assert again[date(2026, 10, 21)].inference_cost == Decimal("0.1")
