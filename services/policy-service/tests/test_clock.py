from datetime import UTC, datetime

from platform_common.clock import format_beijing


def test_format_beijing_from_utc():
    value = datetime(2026, 9, 18, 7, 36, 8, tzinfo=UTC)
    assert format_beijing(value) == "2026-09-18 15:36:08"


def test_format_beijing_from_iso_string():
    assert format_beijing("2026-09-18T07:36:08.075954+00:00") == "2026-09-18 15:36:08"
