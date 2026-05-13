"""
Pre-market gap scanner.

Computes for each instrument:
  prev_close, today_open (or pre-market reference price), gap_pct
Sorts by absolute gap and returns the top N candidates.

Data:
  We use Angel One historical candles for prev close.
  At 09:15-09:16 IST we then fetch the first 1-min candle to get today's open.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.broker.angel_client import AngelClient
from src.universe.fno_universe import Instrument
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


def fetch_prev_close(client: AngelClient, instruments: list[Instrument]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ins in instruments:
        try:
            data = client.candles(ins.token, "ONE_DAY", days_back=10)
            if data:
                # last completed daily candle
                last = data[-1]
                # candle row: [timestamp, open, high, low, close, volume]
                out[ins.symbol] = float(last[4])
        except Exception as e:
            log.debug("prev_close failed for %s: %s", ins.symbol, e)
    return out


def scan_gaps(client: AngelClient, instruments: list[Instrument],
              prev_close: dict[str, float], top_n: int = 25) -> list[GapRow]:
    rows: list[GapRow] = []
    for ins in instruments:
        pc = prev_close.get(ins.symbol)
        if not pc:
            continue
        try:
            ltp = client.ltp(ins.exchange, ins.trading_symbol, ins.token)
        except Exception as e:
            log.debug("ltp failed for %s: %s", ins.symbol, e)
            continue
        gap = (ltp - pc) / pc * 100
        rows.append(GapRow(ins.symbol, ins.token, ins.trading_symbol, pc, ltp, gap))
    rows.sort(key=lambda r: abs(r.gap_pct), reverse=True)
    top = rows[:top_n]
    log.info("Gap scan: top %d / %d", len(top), len(rows))
    return top
