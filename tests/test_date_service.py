from datetime import datetime
from services.date_service import get_current_datetime, get_current_datetime_str, DEFAULT_TIMEZONE


def test_get_current_datetime():
    dt = get_current_datetime()
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


def test_get_current_datetime_str():
    dt_str = get_current_datetime_str()
    assert isinstance(dt_str, str)
    # Check format: YYYY-MM-DD HH:MM:SS Day
    parts = dt_str.split(" ")
    assert len(parts) >= 2
    # First part is date YYYY-MM-DD
    assert len(parts[0].split("-")) == 3


def test_format_local_datetime_converts_utc_to_vietnam_time():
    from datetime import datetime, timezone
    from services.date_service import format_local_datetime

    assert format_local_datetime(datetime(2026, 9, 9, 9, 28, 21, tzinfo=timezone.utc)) == "2026-09-09 16:28:21 +07"
