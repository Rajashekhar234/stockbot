"""
Opening Range Breakout (09:15-09:30) detector.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.broker.angel_client import AngelClient
from src.utils.logger import get_logger

log = get_logger("orb")


@dataclass
class OpeningRange:
    symbol: str
    or_high: float
    or_low: float
    or_volume: int


def compute_opening_range(client: AngelClient, token: str, symbol: str) -> OpeningRange | None:
    """Pull the three 5-min candles 09:15, 09:20, 09:25 and aggregate."""
    try:
        data = client.candles(token, "FIVE_MINUTE", days_back=1)
    except Exception as e:
        log.debug("ORB candles failed for %s: %s", symbol, e)
        return None

    today = data[-3:] if len(data) >= 3 else data
    if not today:
        return None
    high = max(float(c[2]) for c in today)
    low = min(float(c[3]) for c in today)
    vol = sum(int(c[5]) for c in today)
    return OpeningRange(symbol, high, low, vol)


def is_breakout(ltp: float, opening: OpeningRange, direction: str = "UP") -> bool:
    if direction == "UP":
        return ltp > opening.or_high
    return ltp < opening.or_low
