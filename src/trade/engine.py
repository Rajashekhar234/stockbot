"""
Trade engine — entry, exit, position bookkeeping.

Modes:
  PAPER       — simulated, only logs
  LIVE        — calls Angel One placeOrder
  ALERT_ONLY  — neither, just notifies
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from threading import Lock

from config import LOG_DIR, settings
from src.alerts.notifier import Notifier
from src.broker.angel_client import AngelClient
from src.control import state
from src.utils.logger import get_logger
from src.utils.market_time import now_ist, today_at

log = get_logger("trade")

LEDGER = Path(LOG_DIR) / f"trades_{datetime.now():%Y%m%d}.csv"


@dataclass
class Position:
    symbol: str
    token: str
    trading_symbol: str
    qty: int
    entry_price: float
    sl_price: float
    target_price: float
    high_watermark: float
    entered_at: datetime
    score: int
    note: str = ""


class TradeEngine:
    def __init__(self, broker: AngelClient | None, notifier: Notifier):
        self.broker = broker
        self.notifier = notifier
        self.positions: dict[str, Position] = {}
        self._lock = Lock()
        self._init_ledger()

    # ------------------------------------------------- ledger
    def _init_ledger(self):
        if not LEDGER.exists():
            LEDGER.write_text(
                "ts,event,symbol,qty,price,sl,target,score,pnl,note\n", encoding="utf-8"
            )

    def _record(self, event: str, p: Position, price: float, pnl: float = 0.0, note: str = ""):
        with LEDGER.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([now_ist().isoformat(timespec="seconds"), event, p.symbol,
                        p.qty, f"{price:.2f}", f"{p.sl_price:.2f}",
                        f"{p.target_price:.2f}", p.score, f"{pnl:.2f}", note])

    # ------------------------------------------------- sizing
    def _qty_for(self, price: float) -> int:
        if settings.trade_amount > 0:
            budget = settings.trade_amount
        else:
            budget = settings.capital * settings.max_position_pct
        qty = int(budget // price)
        if settings.max_qty > 0:
            qty = min(qty, settings.max_qty)
        return max(0, qty)

    # ------------------------------------------------- entry
    def open_long(self, *, symbol: str, token: str, trading_symbol: str,
                  ltp: float, score: int, note: str = "") -> Position | None:
        with self._lock:
            if state.is_paused():
                log.info("Skip %s — bot is PAUSED via Telegram", symbol)
                return None
            if symbol in self.positions:
                return None
            if self.positions:
                log.info("Skip %s — already holding %s", symbol, list(self.positions))
                return None
            qty = self._qty_for(ltp)
            if qty <= 0:
                log.warning("Insufficient capital for %s @ %.2f", symbol, ltp)
                return None

            sl = round(ltp * (1 - settings.stop_loss_pct), 2)
            tgt = round(ltp * (1 + settings.target_pct), 2)
            pos = Position(symbol, token, trading_symbol, qty, ltp, sl, tgt,
                           ltp, now_ist(), score, note)

            if settings.trade_mode == "LIVE" and self.broker:
                try:
                    self.broker.place_market_buy(trading_symbol, token, qty)
                except Exception as e:
                    log.error("LIVE buy failed for %s: %s", symbol, e)
                    return None

            self.positions[symbol] = pos
            self._record("BUY", pos, ltp, note=note)
            self.notifier.alert(
                f"BUY {symbol} x{qty} @ ₹{ltp:.2f}  | SL ₹{sl:.2f}  TGT ₹{tgt:.2f}  | score {score}\n{note}"
            )
            return pos

    # ------------------------------------------------- exit
    def on_tick(self, tick: dict) -> None:
        sym = tick["symbol"]
        ltp = tick["ltp"]
        with self._lock:
            pos = self.positions.get(sym)
            if not pos:
                return

            # Trailing SL once price is +1.5%
            if ltp >= pos.entry_price * (1 + settings.trail_after_pct):
                if ltp > pos.high_watermark:
                    pos.high_watermark = ltp
                trail_sl = round(pos.high_watermark * (1 - settings.stop_loss_pct), 2)
                if trail_sl > pos.sl_price:
                    pos.sl_price = trail_sl

            if ltp <= pos.sl_price:
                self._close(pos, ltp, "STOP_LOSS")
            elif ltp >= pos.target_price:
                self._close(pos, ltp, "TARGET")

    def maybe_force_exit(self) -> None:
        if now_ist() < today_at(settings.force_exit_time):
            return
        with self._lock:
            for sym, pos in list(self.positions.items()):
                self._close(pos, pos.entry_price, "FORCE_EOD")

    def _close(self, pos: Position, price: float, reason: str) -> None:
        pnl = (price - pos.entry_price) * pos.qty
        if settings.trade_mode == "LIVE" and self.broker:
            try:
                self.broker.place_market_sell(pos.trading_symbol, pos.token, pos.qty)
            except Exception as e:
                log.error("LIVE sell failed for %s: %s", pos.symbol, e)
        self._record(reason, pos, price, pnl, reason)
        self.notifier.alert(
            f"EXIT {pos.symbol} @ ₹{price:.2f}  | {reason}  | P&L ₹{pnl:+.2f}"
        )
        self.positions.pop(pos.symbol, None)
