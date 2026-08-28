from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def get_current_datetime(tz: ZoneInfo = DEFAULT_TIMEZONE) -> datetime:
    return datetime.now(tz)


def get_current_datetime_str(tz: ZoneInfo = DEFAULT_TIMEZONE) -> str:
    now = get_current_datetime(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %A")