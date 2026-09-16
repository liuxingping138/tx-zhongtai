from __future__ import annotations

from datetime import timedelta

from app.domain.enums import OutboxStatus


def next_retry_delay(*, attempts: int, base_seconds: int, cap_seconds: int) -> timedelta:
    exponent = max(attempts - 1, 0)
    seconds = min(cap_seconds, base_seconds * (2**exponent))
    return timedelta(seconds=seconds)


def should_park(*, attempts: int, max_attempts: int) -> bool:
    return attempts >= max_attempts


def next_status(*, attempts: int, max_attempts: int) -> str:
    return OutboxStatus.DEAD if should_park(attempts=attempts, max_attempts=max_attempts) else OutboxStatus.FAILED
