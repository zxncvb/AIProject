from datetime import datetime, timezone

import pytest

from app.services.workflow import next_cron_occurrence, next_schedule_time


def test_interval_schedule_advances_from_base():
    base = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
    assert next_schedule_time("", "UTC", 60, base) == datetime(2026, 10, 23, 8, 1, tzinfo=timezone.utc)


def test_cron_schedule_uses_timezone():
    base = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
    # 09:00 Asia/Shanghai is 01:00 UTC.
    assert next_cron_occurrence("0 9 * * *", "Asia/Shanghai", base) == datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)


def test_cron_schedule_supports_steps_and_or_day_matching():
    base = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
    assert next_cron_occurrence("*/15 * * * *", "UTC", base) == datetime(2026, 10, 23, 8, 15, tzinfo=timezone.utc)
    # When both day-of-month and weekday are restricted, cron uses OR semantics.
    assert next_cron_occurrence("0 9 1 * 5", "UTC", base) == datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def test_cron_schedule_rejects_invalid_expression():
    with pytest.raises(ValueError):
        next_cron_occurrence("0 9 *", "UTC", datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        next_cron_occurrence("0 9 * * *", "Not/AZone", datetime.now(timezone.utc))
