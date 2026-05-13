"""
Angel One SmartWebSocket V2 wrapper.

Subscribes to up to 50 NSE-EQ tokens and pushes ticks into a queue
that the trade engine consumes.

Each tick dict: {symbol, token, ltp, volume, ts}
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

from src.broker.angel_client import AngelClient
from src.utils.logger import get_logger

log = get_logger("ws")


class TickStream:
    NSE_CM = 1   # exchange type for NSE cash
    MODE_LTP = 1
    MODE_QUOTE = 2
    MODE_FULL = 3

    def __init__(self, client: AngelClient, token_to_symbol: dict[str, str]):
        self.client = client
        self.map = token_to_symbol
        self.q: queue.Queue[dict] = queue.Queue(maxsize=10_000)
        self._ws = None
        self._thread: threading.Thread | None = None
        self._on_tick: Callable[[dict], None] | None = None

    # -------------------------------------------------- callbacks
    def _on_data(self, _wsapp, message):
        try:
            sym = self.map.get(str(message.get("token")), "?")
            tick = {
                "symbol": sym,
                "token": str(message.get("token")),
                "ltp": float(message.get("last_traded_price", 0)) / 100,
                "volume": int(message.get("volume_trade_for_the_day", 0) or 0),
                "ts": message.get("exchange_timestamp"),
            }
            self.q.put_nowait(tick)
            if self._on_tick:
                self._on_tick(tick)
        except Exception as e:
            log.debug("on_data error: %s", e)

    def _on_open(self, _wsapp):
        tokens = list(self.map.keys())
        log.info("WS open — subscribing %d tokens", len(tokens))
        token_list = [{"exchangeType": self.NSE_CM, "tokens": tokens[:50]}]
        self._ws.subscribe("stockbot", self.MODE_QUOTE, token_list)

    def _on_error(self, _wsapp, err):
        log.error("WS error: %s", err)

    def _on_close(self, _wsapp):
        log.warning("WS closed")

    # -------------------------------------------------- lifecycle
    def start(self, on_tick: Callable[[dict], None] | None = None) -> None:
        self._on_tick = on_tick
        self._ws = self.client.make_ws()
        self._ws.on_data = self._on_data
        self._ws.on_open = self._on_open
        self._ws.on_error = self._on_error
        self._ws.on_close = self._on_close

        self._thread = threading.Thread(target=self._ws.connect, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            if self._ws:
                self._ws.close_connection()
        except Exception:
            pass
