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
