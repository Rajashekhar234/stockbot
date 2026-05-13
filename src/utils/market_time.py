"""IST market-clock helpers."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def today_at(t: time) -> datetime:
    n = now_ist()
    return n.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def is_market_open() -> bool:
    n = now_ist().time()
    return time(9, 15) <= n <= time(15, 30)


def is_weekday() -> bool:
    return now_ist().weekday() < 5
