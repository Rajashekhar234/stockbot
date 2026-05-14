"""
Bot safety helpers — startup banner, monthly summary, holiday gate.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from config import LOG_DIR, settings
from src.utils.logger import get_logger

log = get_logger("safety")


def print_startup_banner() -> None:
    """Big visible banner so the user sees exactly what the bot will do today."""
    eff_qty_at = lambda price: int((settings.trade_amount or 0) // price)
    cap_or_amt = (
        f"TRADE_AMOUNT = ₹{settings.trade_amount:,.0f}  "
        f"(qty@₹500 = {eff_qty_at(500)}, qty@₹1500 = {eff_qty_at(1500)})"
        if settings.trade_amount > 0
        else f"CAPITAL = ₹{settings.capital:,.0f}  ×  {settings.max_position_pct*100:.0f}%"
    )
    bar = "═" * 70
    log.info(bar)
    log.info("  STOCK BOT — daily session starting")
    log.info(bar)
    log.info("  Mode            : %s", settings.trade_mode)
    log.info("  Sizing          : %s", cap_or_amt)
    log.info("  Stop Loss       : -%.2f%%   Target: +%.2f%%   Trail after: +%.2f%%",
             settings.stop_loss_pct * 100, settings.target_pct * 100,
             settings.trail_after_pct * 100)
    log.info("  Force exit time : %s", settings.force_exit_time)
    log.info("  Universe band   : ₹%.0f - ₹%.0f", settings.min_price, settings.max_price)
    log.info("  Min score       : %d / 100", settings.min_score)
    log.info("  Telegram ctrl   : %s", "ON" if settings.telegram_admin_ids else "off")
    log.info(bar)


def write_monthly_summary() -> Path | None:
    """Aggregate today's + earlier daily ledgers into a monthly CSV summary."""
    month = datetime.now().strftime("%Y%m")
    rows: list[dict] = []
    for f in Path(LOG_DIR).glob(f"trades_{month[:6]}*.csv"):
        try:
            with f.open(encoding="utf-8") as fh:
                rows.extend(csv.DictReader(fh))
        except Exception as e:
            log.debug("skip %s: %s", f, e)

    closes = [r for r in rows if r.get("event") in {"STOP_LOSS", "TARGET", "FORCE_EOD", "USER_STOP"}]
    if not closes:
        log.info("Monthly summary: no closed trades for %s", month)
        return None

    pnls = [float(r.get("pnl") or 0) for r in closes]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    out = Path(LOG_DIR) / f"monthly_summary_{month}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Month", "Trades", "Wins", "Losses", "WinRate%",
                    "Net_PnL", "Avg_Win", "Avg_Loss", "Best", "Worst"])
        w.writerow([
            month, len(closes), len(wins), len(losses),
            round(len(wins) / len(closes) * 100, 1),
            round(sum(pnls), 2),
            round(sum(wins) / len(wins), 2) if wins else 0,
            round(sum(losses) / len(losses), 2) if losses else 0,
            round(max(pnls), 2),
            round(min(pnls), 2),
        ])
    log.info("Monthly summary written: %s  (trades=%d, win-rate=%.1f%%, net=₹%.2f)",
             out, len(closes), len(wins) / len(closes) * 100, sum(pnls))
    return out
