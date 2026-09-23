from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def get_current_datetime(tz: ZoneInfo = DEFAULT_TIMEZONE) -> datetime:
    return datetime.now(tz)


def get_current_datetime_str(tz: ZoneInfo = DEFAULT_TIMEZONE) -> str:
    now = get_current_datetime(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %A")

def format_local_datetime(value: datetime | None) -> str | None:
    """Format a persisted timestamp in the application timezone.

    PostgreSQL timestamps are stored in UTC.  Naive values are treated as UTC
    for compatibility with legacy SQLite records before conversion.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DEFAULT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
