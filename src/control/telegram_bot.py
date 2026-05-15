"""
Telegram bot — long-poll for /commands.

Commands (admin-only):
  /status     → current state, capital, mode, open positions
  /pause      → block any new entries (existing positions still managed)
  /resume     → re-enable new entries
  /stop       → graceful shutdown after current trade closes
  /positions  → list open positions
  /help       → command list
"""
from __future__ import annotations

import threading
import time

import requests

from config import settings
from src.control import state
from src.control.tg_config import SAFE_KEYS, list_keys, set_value, show_config
from src.utils.logger import get_logger

log = get_logger("tg-cmd")

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramController:
    def __init__(self, engine_ref) -> None:
        """engine_ref is a TradeEngine; we read positions from it."""
        self.engine = engine_ref
        self._offset = 0
        self._thread: threading.Thread | None = None
        self._stopped = False
        self._admins = {x.strip() for x in settings.telegram_admin_ids.split(",") if x.strip()}

    @property
    def enabled(self) -> bool:
        return bool(settings.telegram_bot_token and self._admins)

    # ---------------------------------------------------- lifecycle
    def start(self) -> None:
        if not self.enabled:
            log.info("Telegram control disabled (no token / admin ids)")
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Telegram command listener started for admins=%s", self._admins)
        self._send(f"\U0001F916 StockBot online. Mode={settings.trade_mode}. Send /help.")

    def stop(self) -> None:
        self._stopped = True

    # ---------------------------------------------------- internals
    def _api(self, method: str, **params) -> dict:
        url = _API.format(token=settings.telegram_bot_token, method=method)
        try:
            r = requests.get(url, params=params, timeout=35)
            return r.json()
        except Exception as e:
            log.debug("telegram api %s failed: %s", method, e)
            return {}

    def _send(self, text: str, chat_id: str | None = None) -> None:
        cid = chat_id or settings.telegram_chat_id
        if not cid:
            return
        self._api("sendMessage", chat_id=cid, text=text)

    def _loop(self) -> None:
        while not self._stopped:
            try:
                resp = self._api("getUpdates", offset=self._offset, timeout=30)
                for upd in resp.get("result", []):
                    self._offset = upd["update_id"] + 1
                    self._handle(upd)
            except Exception as e:
                log.debug("poll error: %s", e)
                time.sleep(3)

    def _handle(self, upd: dict) -> None:
        msg = upd.get("message") or upd.get("edited_message") or {}
        text = (msg.get("text") or "").strip()
        chat = str(msg.get("chat", {}).get("id", ""))
        sender = str(msg.get("from", {}).get("id", ""))
        if not text.startswith("/"):
            return
        if sender not in self._admins:
            self._send("Unauthorized.", chat_id=chat)
            log.warning("Unauthorized /command from %s: %s", sender, text)
            return

        cmd = text.split()[0].lower().split("@")[0]
        args = text.split()[1:]

        # /set<key> <value>  (e.g. /setamount 25000)
        if cmd.startswith("/set") and cmd != "/setup":
            key = cmd[4:]
            if not args:
                self._send(f"Usage: {cmd} <value>")
                return
            self._send(set_value(key, args[0]))
            return

        if cmd == "/help":
            self._send(
                "Control:\n"
                "  /status /pause /resume /stop /positions\n"
                "Config:\n"
                "  /config       — show current values\n"
                "  /settings     — list editable keys\n"
                "  /set<key> <v> — e.g. /setamount 25000, /setmode PAPER"
            )
        elif cmd == "/status":
            s = state.snapshot()
            self._send(
                f"mode={settings.trade_mode}\n"
                f"paused={s['paused']}  stopping={s['stopping']}\n"
                f"trade_amount=\u20b9{settings.trade_amount or 'pct'}\n"
                f"open_positions={len(self.engine.positions)}"
            )
        elif cmd == "/pause":
            state.pause(reason=f"telegram by {sender}")
            self._send("\u23F8\uFE0F Paused. No new entries until /resume.")
        elif cmd == "/resume":
            state.resume()
            self._send("\u25B6\uFE0F Resumed. New entries allowed.")
        elif cmd == "/stop":
            state.request_stop(reason=f"telegram by {sender}")
            self._send("\U0001F6D1 Stop requested. Bot will exit after current cycle.")
        elif cmd == "/positions":
            if not self.engine.positions:
                self._send("No open positions.")
            else:
                lines = [
                    f"{p.symbol} x{p.qty} @ \u20b9{p.entry_price:.2f}  SL \u20b9{p.sl_price:.2f}  TGT \u20b9{p.target_price:.2f}"
                    for p in self.engine.positions.values()
                ]
                self._send("\n".join(lines))
        elif cmd == "/config":
            self._send(show_config())
        elif cmd == "/settings":
            self._send(list_keys())
        else:
            self._send(f"Unknown command: {cmd}")
