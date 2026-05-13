"""
GIFT Nifty pre-market sentiment (formerly SGX Nifty).

Per strategy doc:
  * GIFT Nifty +/- vs prior Nifty close indicates expected gap
  * If GIFT Nifty < -200 → bearish day, DO NOT TRADE

We scrape investing.com's lightweight quote endpoint. If it fails, we
return a neutral bias so trading is allowed but the user is warned.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from src.utils.logger import get_logger

log = get_logger("gift")

_URL = "https://www.investing.com/indices/sgx-nifty-50-futures"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}


@dataclass
class GiftSnapshot:
    last: float | None
    change_pts: float | None
    change_pct: float | None
    bias: str  # BULLISH / NEUTRAL / BEARISH / UNKNOWN

    @property
    def trade_allowed(self) -> bool:
        return self.bias != "BEARISH"


def fetch_gift_nifty() -> GiftSnapshot:
    try:
        from bs4 import BeautifulSoup
        r = requests.get(_URL, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        last = _parse_float(soup.select_one('[data-test="instrument-price-last"]'))
        chg = _parse_float(soup.select_one('[data-test="instrument-price-change"]'))
        chgp = _parse_float(soup.select_one('[data-test="instrument-price-change-percent"]'))
        bias = _classify(chg)
        return GiftSnapshot(last, chg, chgp, bias)
    except Exception as e:
        log.warning("GIFT Nifty fetch failed (%s) — assuming UNKNOWN", e)
        return GiftSnapshot(None, None, None, "UNKNOWN")


def _parse_float(el) -> float | None:
    if not el:
        return None
    txt = el.get_text(strip=True).replace(",", "").replace("%", "").replace("(", "").replace(")", "")
    try:
        return float(txt)
    except ValueError:
        return None


def _classify(chg: float | None) -> str:
    if chg is None:
        return "UNKNOWN"
    if chg <= -200:
        return "BEARISH"
    if chg >= 100:
        return "BULLISH"
    return "NEUTRAL"
