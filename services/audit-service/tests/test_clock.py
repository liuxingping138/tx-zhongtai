from datetime import UTC, datetime

from app.core.clock import assume_beijing


def test_assume_beijing_naive():
    value = assume_beijing(datetime(2026, 9, 18, 15, 0, 0))
    assert value is not None
    assert value.utcoffset().total_seconds() == 8 * 3600


def test_assume_beijing_keeps_aware():
    utc = datetime(2026, 9, 18, 7, 0, 0, tzinfo=UTC)
    value = assume_beijing(utc)
    assert value == utc
