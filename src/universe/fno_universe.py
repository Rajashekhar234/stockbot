"""
Build the daily F&O cash-equity universe.

Strategy doc rules:
  * Only NSE 'EQ' series (skip BE / T2T)
  * Price band ₹MIN_PRICE - ₹MAX_PRICE
  * Stock must be in NSE F&O list (~180 names)

Sources:
  * Angel One scrip master JSON (instruments + tokens)
  * NSE F&O underlyings CSV  (https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv)

Both are cached daily under data/cache/.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from config import CACHE_DIR, settings
from src.utils.logger import get_logger

log = get_logger("universe")

ANGEL_SCRIP_MASTER = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
NSE_FNO_LOTS = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


@dataclass
class Instrument:
    symbol: str          # e.g. RELIANCE
    trading_symbol: str  # e.g. RELIANCE-EQ
    token: str           # Angel one token
    exchange: str        # NSE
    lot_size: int = 1


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{date.today():%Y-%m-%d}_{name}"


def _download(url: str, cache_name: str, headers: dict | None = None) -> bytes:
    p = _cache_path(cache_name)
    if p.exists():
        return p.read_bytes()
    log.info("Downloading %s", url)
    r = requests.get(url, headers=headers or {}, timeout=30)
    r.raise_for_status()
    p.write_bytes(r.content)
    return r.content


def load_fno_symbols() -> set[str]:
    """Returns the set of NSE underlying symbols that have F&O contracts."""
    try:
        raw = _download(NSE_FNO_LOTS, "fno_lots.csv", _NSE_HEADERS).decode("utf-8", "ignore")
    except Exception as e:
        log.warning("NSE fetch failed (%s) — falling back to bundled list", e)
        return _bundled_fno_fallback()

    symbols: set[str] = set()
    reader = csv.reader(io.StringIO(raw))
    for row in reader:
        if not row or len(row) < 2:
            continue
        sym = row[1].strip().upper()
        # Skip header rows / index rows / blanks
        if not sym or sym in {"SYMBOL", "UNDERLYING"} or " " in sym:
            continue
        if sym in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}:
            continue
        symbols.add(sym)
    log.info("Loaded %d F&O underlyings from NSE", len(symbols))
    return symbols


def _bundled_fno_fallback() -> set[str]:
    """Tiny fallback list so the bot still runs when NSE is unreachable."""
    return {
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK",
        "KOTAKBANK", "ITC", "LT", "HINDUNILVR", "BAJFINANCE", "MARUTI", "TATAMOTORS",
        "TATASTEEL", "WIPRO", "HCLTECH", "TECHM", "ULTRACEMCO", "ASIANPAINT",
        "ADANIENT", "ADANIPORTS", "BHARTIARTL", "POWERGRID", "NTPC", "ONGC",
        "COALINDIA", "M&M", "SUNPHARMA", "DRREDDY", "CIPLA", "NESTLEIND",
        "TITAN", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "DIVISLAB", "GRASIM",
        "JSWSTEEL", "HINDALCO", "VEDL", "BPCL", "IOC", "GAIL", "PIDILITIND",
        "DABUR", "BRITANNIA", "GODREJCP", "MARICO", "INDUSINDBK", "MRPL",
    }


def build_universe(angel_client=None) -> list[Instrument]:
    """Returns Instruments to monitor today."""
    fno = load_fno_symbols()

    raw = _download(ANGEL_SCRIP_MASTER, "angel_scrip.json").decode("utf-8", "ignore")
    scrips = json.loads(raw)

    instruments: list[Instrument] = []
    seen = set()
    for s in scrips:
        if s.get("exch_seg") != "NSE":
            continue
        ts = (s.get("symbol") or "").upper()        # e.g. RELIANCE-EQ
        if not ts.endswith("-EQ"):                  # series must be EQ
            continue
        base = ts[:-3]
        if base in seen or base not in fno:
            continue
        seen.add(base)
        instruments.append(
            Instrument(
                symbol=base,
                trading_symbol=ts,
                token=str(s.get("token")),
                exchange="NSE",
                lot_size=int(s.get("lotsize") or 1),
            )
        )

    log.info("Universe built: %d EQ instruments mapped to F&O underlyings", len(instruments))
    return instruments


def filter_by_price(instruments: list[Instrument], prev_close: dict[str, float]) -> list[Instrument]:
    """Keep only stocks whose last close is within configured price band."""
    out = []
    for ins in instruments:
        p = prev_close.get(ins.symbol)
        if p is None:
            continue
        if settings.min_price <= p <= settings.max_price:
            out.append(ins)
    log.info("Price-band filter %.0f-%.0f → %d / %d remain",
             settings.min_price, settings.max_price, len(out), len(instruments))
    return out
