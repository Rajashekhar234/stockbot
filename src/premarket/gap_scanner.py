"""
Pre-market gap scanner.

NEW (May 2026): pulls NSE Pre-Open Market data which already contains:
  symbol, prev_close, IEP (open), gap %, finalQuantity, totalTurnover

This is the official source the user described:
  https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market

Index keys you can pick (set NSE_INDEX_KEY in .env):
  FO        — F&O underlyings (RECOMMENDED, ~180 stocks)
  NIFTY     — NIFTY 50
  ALL       — every NSE pre-open quote (~2000 stocks, slow)

Gap %, opening price and prev close are read straight from NSE — no Angel
calls needed for the pre-market scan. Angel is still used later for ORB,
LTP and order placement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.broker.angel_client import AngelClient
from src.universe.fno_universe import Instrument
from src.universe.nse_client import NSEClient, PreOpenRow
from src.utils.logger import get_logger

log = get_logger("gap")


@dataclass
class GapRow:
    symbol: str
    token: str
    trading_symbol: str
    prev_close: float
    open_price: float
    gap_pct: float
    pre_open_qty: int = 0
    pre_open_turnover: float = 0.0


def fetch_pre_open_rows(index_key: str | None = None) -> list[PreOpenRow]:
    key = (index_key or os.getenv("NSE_INDEX_KEY", "FO")).upper()
    return NSEClient().pre_open(key)


def fetch_prev_close_from_nse(rows: list[PreOpenRow]) -> dict[str, float]:
    return {r.symbol: r.prev_close for r in rows if r.prev_close > 0}


def scan_gaps(instruments: list[Instrument],
              pre_open: list[PreOpenRow] | None = None,
              top_n: int = 25) -> list[GapRow]:
    """Sort by absolute gap and return the top N candidates that are also in our universe."""
    if pre_open is None:
        pre_open = fetch_pre_open_rows()

    if not pre_open:
        log.warning("No pre-open data — cannot run gap scan")
        return []

    by_sym = {p.symbol: p for p in pre_open if p.series == "EQ"}
    rows: list[GapRow] = []
    for ins in instruments:
        p = by_sym.get(ins.symbol)
        if not p or p.open_price <= 0 or p.prev_close <= 0:
            continue
        rows.append(GapRow(
            symbol=ins.symbol,
            token=ins.token,
            trading_symbol=ins.trading_symbol,
            prev_close=p.prev_close,
            open_price=p.open_price,
            gap_pct=p.change_pct,
            pre_open_qty=p.final_qty,
            pre_open_turnover=p.total_turnover,
        ))

    rows.sort(key=lambda r: abs(r.gap_pct), reverse=True)
    top = rows[:top_n]
    log.info("Gap scan: top %d / %d (best gap %.2f%%)",
             len(top), len(rows), top[0].gap_pct if top else 0)
    return top


# ---- backwards-compat helper used by orchestrator ---------------------------
def fetch_prev_close(_client: AngelClient, _instruments: list[Instrument]) -> dict[str, float]:
    """Now sourced from NSE pre-open instead of Angel daily candles."""
    return fetch_prev_close_from_nse(fetch_pre_open_rows())
