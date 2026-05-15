"""
Central configuration. Loads .env once and exposes typed settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
for d in (LOG_DIR, DATA_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _get(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _get_float(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    try:
        return int(float(_get(key, str(default))))
    except ValueError:
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    return _get(key, str(default)).lower() in ("1", "true", "yes", "y", "on")


def _get_time(key: str, default: str) -> time:
    raw = _get(key, default)
    h, m = raw.split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Settings:
    # Angel One
    angel_api_key: str = _get("ANGEL_API_KEY")
    angel_client_code: str = _get("ANGEL_CLIENT_CODE")
    angel_password: str = _get("ANGEL_PASSWORD")
    angel_totp_secret: str = _get("ANGEL_TOTP_SECRET")
    angel_mpin: str = _get("ANGEL_MPIN")

    # Gemini
    gemini_api_key: str = _get("GEMINI_API_KEY")
    gemini_model: str = _get("GEMINI_MODEL", "gemini-2.0-flash")

    # Mode
    trade_mode: str = _get("TRADE_MODE", "PAPER").upper()  # PAPER / LIVE / ALERT_ONLY

    # Capital & risk
    capital: float = _get_float("CAPITAL", 20000)
    trade_amount: float = _get_float("TRADE_AMOUNT", 0)  # 0 = use percentage
    max_qty: int = _get_int("MAX_QTY", 0)                # 0 = no cap
    max_position_pct: float = _get_float("MAX_POSITION_PCT", 0.80)
    stop_loss_pct: float = _get_float("STOP_LOSS_PCT", 0.01)
    target_pct: float = _get_float("TARGET_PCT", 0.025)
    trail_after_pct: float = _get_float("TRAIL_AFTER_PCT", 0.015)
    force_exit_time: time = _get_time("FORCE_EXIT_TIME", "15:00")

    # Universe
    universe_mode: str = _get("UNIVERSE_MODE", "BROAD").upper()  # BROAD | FNO
    min_price: float = _get_float("MIN_PRICE", 100)
    max_price: float = _get_float("MAX_PRICE", 5000)
    min_preopen_value: float = _get_float("MIN_PREOPEN_VALUE", 10_00_000)  # 10 lakh
    max_candidates: int = _get_int("MAX_CANDIDATES", 25)

    # Score
    min_score: int = _get_int("MIN_SCORE", 80)

    # Alerts
    telegram_bot_token: str = _get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = _get("TELEGRAM_CHAT_ID")
    telegram_admin_ids: str = _get("TELEGRAM_ADMIN_IDS")
    enable_sound_alerts: bool = _get_bool("ENABLE_SOUND_ALERTS", True)


settings = Settings()

# Market session constants (IST)
MARKET_OPEN = time(9, 15)
PRE_OPEN_FETCH = time(9, 8)   # NSE pre-open is final at 09:08 IST
ORB_END = time(9, 30)
NO_NEW_TRADE_AFTER = time(14, 30)
MARKET_CLOSE = time(15, 30)
