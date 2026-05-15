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
from config import settings

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
    # In BROAD mode, pull every NSE pre-open quote so micro-mid caps get a shot.
    default_key = "ALL" if settings.universe_mode == "BROAD" else "FO"
    key = (index_key or os.getenv("NSE_INDEX_KEY", default_key)).upper()
    return NSEClient().pre_open(key)


def fetch_prev_close_from_nse(rows: list[PreOpenRow]) -> dict[str, float]:
    return {r.symbol: r.prev_close for r in rows if r.prev_close > 0}


def scan_gaps(instruments: list[Instrument],
              pre_open: list[PreOpenRow] | None = None,
              top_n: int | None = None) -> list[GapRow]:
    """Apply anti-penny + liquidity filters, sort gap-up first, return top N."""
    if pre_open is None:
        pre_open = fetch_pre_open_rows()

    if not pre_open:
        log.warning("No pre-open data — cannot run gap scan")
        return []

    top_n = top_n or settings.max_candidates
    by_sym = {p.symbol: p for p in pre_open if p.series == "EQ"}

    rows: list[GapRow] = []
    skipped_price = skipped_liq = skipped_band = 0
    for ins in instruments:
        p = by_sym.get(ins.symbol)
        if not p or p.open_price <= 0 or p.prev_close <= 0:
            continue
        # Anti-penny: enforce hard price band on prev close
        if p.prev_close < settings.min_price:
            skipped_price += 1
            continue
        if p.prev_close > settings.max_price:
            skipped_band += 1
            continue
        # Liquidity gate: pre-open value (qty * price) avoids dust scrips
        po_value = (p.final_qty or 0) * (p.open_price or p.prev_close)
        if po_value < settings.min_preopen_value:
            skipped_liq += 1
            continue
        rows.append(GapRow(
            symbol=ins.symbol,
            token=ins.token,
            trading_symbol=ins.trading_symbol,
            prev_close=p.prev_close,
            open_price=p.open_price,
            gap_pct=p.change_pct,
            pre_open_qty=p.final_qty,
            pre_open_turnover=po_value,
        ))

    # Long-only bot — gap-UP first, then by size
    rows.sort(key=lambda r: (r.gap_pct < 0, -r.gap_pct))
    top = rows[:top_n]
    log.info(
        "Gap scan: %d eligible (skipped: penny=%d, above-band=%d, illiquid=%d) — top %d",
        len(rows), skipped_price, skipped_band, skipped_liq, len(top),
    )
    if top:
        log.info("Best: %s gap %+.2f%%", top[0].symbol, top[0].gap_pct)
    return top


# ---- backwards-compat helper used by orchestrator ---------------------------
def fetch_prev_close(_client: AngelClient, _instruments: list[Instrument]) -> dict[str, float]:
    """Now sourced from NSE pre-open instead of Angel daily candles."""
    return fetch_prev_close_from_nse(fetch_pre_open_rows())
