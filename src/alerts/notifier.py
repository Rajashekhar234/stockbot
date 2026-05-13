"""Console + optional Telegram alerts + optional Windows beep."""
from __future__ import annotations

import sys

import requests

from config import settings
from src.utils.logger import get_logger

log = get_logger("alert")


class Notifier:
    def alert(self, msg: str) -> None:
        log.info("ALERT: %s", msg.replace("\n", " | "))
        self._beep()
        self._telegram(msg)

    def _beep(self) -> None:
        if not settings.enable_sound_alerts:
            return
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.Beep(1200, 250)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass

    def _telegram(self, msg: str) -> None:
        if not (settings.telegram_bot_token and settings.telegram_chat_id):
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": settings.telegram_chat_id,
                                     "text": msg}, timeout=10)
        except Exception as e:
            log.debug("telegram send failed: %s", e)
