"""Volume shocker detection — today's pace vs 20-day average."""
from __future__ import annotations

from src.broker.angel_client import AngelClient
from src.utils.logger import get_logger

log = get_logger("volume")


def avg_daily_volume(client: AngelClient, token: str, days: int = 20) -> float:
    try:
        data = client.candles(token, "ONE_DAY", days_back=days + 5)
    except Exception:
        return 0.0
    vols = [int(c[5]) for c in data[-days:]] if data else []
    return sum(vols) / len(vols) if vols else 0.0


def volume_multiplier(today_vol: int, avg_vol: float) -> float:
    if not avg_vol:
        return 0.0
    return today_vol / avg_vol
