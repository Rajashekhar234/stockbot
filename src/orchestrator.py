"""
Daily orchestrator — implements the strategy doc's full routine.

Phase timeline (IST):
  08:55  — pre-flight (universe build, GIFT Nifty, prev close)
  09:15  — market open  (record opening 5-min prints)
  09:30  — opening range complete → score top 10 → start streaming
  09:30-14:30 — live trade engine consumes ticks
  14:30  — block any new entries
  15:00  — force-exit all positions
  15:30  — market close, write summary
"""
from __future__ import annotations

import time as pytime
from datetime import time

from config import MARKET_CLOSE, NO_NEW_TRADE_AFTER, ORB_END, PRE_OPEN_FETCH, settings
from src.ai.gemini_news import analyze as analyze_news
from src.alerts.notifier import Notifier
from src.broker.angel_client import AngelClient
from src.control import state
from src.control.telegram_bot import TelegramController
from src.premarket.gap_scanner import fetch_pre_open_rows, fetch_prev_close_from_nse, scan_gaps
from src.premarket.gift_nifty import fetch_gift_nifty
from src.safety import print_startup_banner, write_monthly_summary
from src.scanner.bull_trap import BullTrapDetector
from src.scanner.orb import compute_opening_range, is_breakout
from src.scanner.scorer import ScoreInputs, score
from src.scanner.volume import avg_daily_volume, volume_multiplier
from src.stream.websocket_feed import TickStream
from src.trade.engine import TradeEngine
from src.universe.fno_universe import build_universe, filter_by_price
from src.universe.nse_client import NSEClient
from src.utils.logger import get_logger
from src.utils.market_time import is_weekday, now_ist, today_at

log = get_logger("orchestrator")


def _wait_until(t: time) -> None:
    target = today_at(t)
    while now_ist() < target:
        pytime.sleep(5)


def run_day(skip_wait: bool = False) -> None:
    print_startup_banner()
    if not is_weekday():
        log.info("Weekend — bot idle.")
        return

    # NSE holiday gate
    try:
        is_hol, desc = NSEClient().is_today_holiday()
        if is_hol:
            log.info("\U0001F389 NSE holiday today (%s) — bot idle.", desc)
            return
    except Exception as e:
        log.warning("Holiday check failed (%s) — continuing", e)

    notifier = Notifier()
    broker_ok = bool(settings.angel_api_key and settings.angel_client_code)
    broker = AngelClient() if broker_ok else None
    if broker:
        try:
            broker.login()
        except Exception as e:
            log.error("Broker login failed → falling back to ALERT_ONLY: %s", e)
            broker = None

    engine = TradeEngine(broker, notifier)
    tg = TelegramController(engine)
    tg.start()

    # 1. Universe ----------------------------------------------------------
    instruments = build_universe()

    # F&O ban list — never trade these today
    try:
        ban = NSEClient().fo_ban_list()
        if ban:
            instruments = [i for i in instruments if i.symbol not in ban]
            log.info("After F&O ban filter: %d instruments", len(instruments))
    except Exception as e:
        log.debug("ban-list fetch failed: %s", e)

    # Wait until 09:08 IST so the NSE pre-open prices are FINAL
    if not skip_wait:
        log.info("Waiting until 09:08 IST for final pre-open prices …")
        _wait_until(PRE_OPEN_FETCH)

    # Single NSE pre-open fetch — gives prev close, open, gap % for everyone
    pre_open_rows = fetch_pre_open_rows()
    prev_close = fetch_prev_close_from_nse(pre_open_rows)
    if prev_close:
        instruments = filter_by_price(instruments, prev_close)
    else:
        log.warning("Pre-open data empty — skipping price-band filter")

    # 2. GIFT Nifty bias ---------------------------------------------------
    gift = fetch_gift_nifty()
    notifier.alert(f"GIFT Nifty bias: {gift.bias}  ({gift.change_pts})")
    if not gift.trade_allowed:
        notifier.alert("Bearish GIFT Nifty (≤ -200) — preserving capital, no new trades.")
        return

    # 3. Wait for opening range to complete -------------------------------
    if not skip_wait:
        log.info("Waiting until 09:30 IST for ORB completion …")
        _wait_until(ORB_END)

    if not broker:
        log.error("Cannot continue without broker (no live ORB / ticks). Exiting.")
        return

    # 4. Gap scan & top candidates (gap-UP first — long-only bot) ---------
    gappers = scan_gaps(instruments, pre_open_rows, top_n=settings.max_candidates)
    bull_trap = BullTrapDetector()

    # 5. Score each candidate ---------------------------------------------
    candidates = []
    for g in gappers:
        opening = compute_opening_range(broker, g.token, g.symbol)
        if not opening:
            continue
        ltp = broker.ltp("NSE", g.trading_symbol, g.token)
        bull_trap.update(g.symbol, ltp)
        if bull_trap.is_rejected(g.symbol):
            log.info("Skip %s — bull trap detected", g.symbol)
            continue
        if not is_breakout(ltp, opening, "UP"):
            continue
        avg_vol = avg_daily_volume(broker, g.token)
        vx = volume_multiplier(opening.or_volume * 75, avg_vol)  # extrapolate to full day
        verdict = analyze_news(g.symbol)
        s = score(ScoreInputs(
            gap_pct=g.gap_pct,
            volume_x=vx,
            orb_break_pct=(ltp - opening.or_high) / opening.or_high * 100,
            above_vwap=True,  # cheap heuristic post-ORB breakout
            news_sentiment=verdict.sentiment,
            gift_bullish=(gift.bias == "BULLISH"),
        ))
        candidates.append((s, g, ltp, verdict))
        log.info("Score %s = %d  (gap %.2f%%  vx %.1f  news=%s)",
                 g.symbol, s, g.gap_pct, vx, verdict.summary)

    candidates.sort(key=lambda x: x[0], reverse=True)
    top_n = settings.max_candidates
    top_picks = candidates[:top_n]
    if not top_picks:
        notifier.alert("No qualifying candidates after ORB — sitting out today.")
        return

    notifier.alert(
        f"Top {len(top_picks)} candidates:\n" + "\n".join(
            f"  {i+1}. {g.symbol}  score={s}  ltp={ltp:.2f}  ({v.summary})"
            for i, (s, g, ltp, v) in enumerate(top_picks)
        )
    )

    # 6. Pick the winner --------------------------------------------------
    best = top_picks[0]
    if best[0] < settings.min_score:
        notifier.alert(f"Best score {best[0]} < threshold {settings.min_score} — no trade.")
        return

    s, g, ltp, verdict = best
    engine.open_long(symbol=g.symbol, token=g.token, trading_symbol=g.trading_symbol,
                     ltp=ltp, score=s, note=verdict.summary)

    # 7. Live monitoring --------------------------------------------------
    token_to_symbol = {g.token: g.symbol for _, g, _, _ in top_picks}
    stream = TickStream(broker, token_to_symbol)
    stream.start(on_tick=engine.on_tick)

    try:
        while now_ist().time() < MARKET_CLOSE:
            if state.is_stopping():
                notifier.alert("Stop signal received — force-exiting positions and shutting down.")
                # close any open trade at last known price
                for sym, pos in list(engine.positions.items()):
                    engine._close(pos, pos.entry_price, "USER_STOP")  # type: ignore[attr-defined]
                break
            engine.maybe_force_exit()
            if (now_ist().time() >= NO_NEW_TRADE_AFTER and not engine.positions):
                pass  # no more entries
            pytime.sleep(2)
    finally:
        stream.stop()
        tg.stop()
        try:
            write_monthly_summary()
        except Exception as e:
            log.debug("monthly summary failed: %s", e)
        notifier.alert("Market closed — bot shutting down. Review logs/trades_*.csv")


if __name__ == "__main__":
    run_day()
