"""
Hot-reloadable trading config from Telegram.

Whitelist of safe keys ONLY — never expose broker secrets / API keys.
Persists changes to .env so they survive bot restart.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import ROOT, settings
from src.utils.logger import get_logger

log = get_logger("tg-cfg")

ENV_FILE = ROOT / ".env"

# (telegram_key, env_key, attr_name, type, validator(min, max), unit)
SAFE_KEYS = {
    "amount":   ("TRADE_AMOUNT",     "trade_amount",     float, (0,        1_00_00_000), "Rs."),
    "minscore": ("MIN_SCORE",        "min_score",        int,   (0,        100),         ""),
    "sl":       ("STOP_LOSS_PCT",    "stop_loss_pct",    float, (0.001,    0.10),        "frac"),
    "target":   ("TARGET_PCT",       "target_pct",       float, (0.001,    0.20),        "frac"),
    "trail":    ("TRAIL_AFTER_PCT",  "trail_after_pct",  float, (0.001,    0.20),        "frac"),
    "maxcand":  ("MAX_CANDIDATES",   "max_candidates",   int,   (1,        100),         ""),
    "minprice": ("MIN_PRICE",        "min_price",        float, (1,        10000),       "Rs."),
    "maxprice": ("MAX_PRICE",        "max_price",        float, (1,        100000),      "Rs."),
    "minpovalue": ("MIN_PREOPEN_VALUE", "min_preopen_value", float, (0, 1_00_00_00_000), "Rs."),
    "mode":     ("TRADE_MODE",       "trade_mode",       str,   None,                    ""),  # PAPER/LIVE/ALERT_ONLY
    "universe": ("UNIVERSE_MODE",    "universe_mode",    str,   None,                    ""),  # BROAD/FNO
}

_VALID_MODES = {"PAPER", "LIVE", "ALERT_ONLY"}
_VALID_UNIVERSE = {"BROAD", "FNO"}


def list_keys() -> str:
    lines = ["Editable settings (use /set<key> <value>):"]
    for k, (env, attr, typ, rng, unit) in SAFE_KEYS.items():
        cur = getattr(settings, attr)
        lines.append(f"  /set{k:<10} cur={cur} {unit}".rstrip())
    return "\n".join(lines)


def show_config() -> str:
    lines = ["Current trading config:"]
    for k, (env, attr, typ, rng, unit) in SAFE_KEYS.items():
        cur = getattr(settings, attr)
        lines.append(f"  {k:<11} = {cur} {unit}".rstrip())
    return "\n".join(lines)


def set_value(key: str, raw: str) -> str:
    """Validate, persist to .env, hot-update settings. Returns user-facing message."""
    if key not in SAFE_KEYS:
        return f"Unknown setting '{key}'. Try /config."

    env_key, attr, typ, rng, _ = SAFE_KEYS[key]

    # Coerce
    try:
        if typ is str:
            value = raw.strip().upper()
        elif typ is int:
            value = int(float(raw))
        else:
            value = float(raw)
    except ValueError:
        return f"Bad value '{raw}' — expected {typ.__name__}."

    # Validate
    if typ is str:
        if attr == "trade_mode" and value not in _VALID_MODES:
            return f"mode must be one of: {', '.join(sorted(_VALID_MODES))}"
        if attr == "universe_mode" and value not in _VALID_UNIVERSE:
            return f"universe must be one of: {', '.join(sorted(_VALID_UNIVERSE))}"
    elif rng is not None:
        lo, hi = rng
        if not (lo <= value <= hi):
            return f"{key}={value} out of range [{lo}, {hi}]"

    old = getattr(settings, attr)
    _persist_to_env(env_key, str(value))

    # Hot-update frozen dataclass via bypass
    object.__setattr__(settings, attr, value)

    log.info("Config update: %s %s -> %s (env %s)", attr, old, value, env_key)
    return f"OK: {key} {old} -> {value}"


def _persist_to_env(key: str, value: str) -> None:
    """Update or insert KEY=value in .env, preserving rest of file."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")

    text = ENV_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    ENV_FILE.write_text(text, encoding="utf-8")
