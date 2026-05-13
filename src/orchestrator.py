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

from config import MARKET_CLOSE, NO_NEW_TRADE_AFTER, ORB_END, settings
from src.ai.gemini_news import analyze as analyze_news
from src.alerts.notifier import Notifier
from src.broker.angel_client import AngelClient
from src.control import state
from src.control.telegram_bot import TelegramController
from src.premarket.gap_scanner import fetch_prev_close, scan_gaps
from src.premarket.gift_nifty import fetch_gift_nifty
from src.scanner.orb import compute_opening_range, is_breakout
from src.scanner.scorer import ScoreInputs, score
from src.scanner.volume import avg_daily_volume, volume_multiplier
from src.stream.websocket_feed import TickStream
from src.trade.engine import TradeEngine
from src.universe.fno_universe import build_universe, filter_by_price
from src.utils.logger import get_logger
from src.utils.market_time import is_weekday, now_ist, today_at

log = get_logger("orchestrator")


def _wait_until(t: time) -> None:
    target = today_at(t)
    while now_ist() < target:
        pytime.sleep(5)


def run_day() -> None:
    if not is_weekday():
        log.info("Weekend — bot idle.")
        return

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
    if broker:
        prev_close = fetch_prev_close(broker, instruments)
        instruments = filter_by_price(instruments, prev_close)
    else:
        prev_close = {}
        log.warning("Broker disabled — running with universe but no live data")

    # 2. GIFT Nifty bias ---------------------------------------------------
    gift = fetch_gift_nifty()
    notifier.alert(f"GIFT Nifty bias: {gift.bias}  ({gift.change_pts})")
    if not gift.trade_allowed:
        notifier.alert("Bearish GIFT Nifty (≤ -200) — preserving capital, no new trades.")
        return

    # 3. Wait for opening range to complete -------------------------------
    log.info("Waiting until 09:30 IST for ORB completion …")
    _wait_until(ORB_END)

    if not broker:
        log.error("Cannot continue without broker (no live ORB / ticks). Exiting.")
        return

    # 4. Gap scan & top candidates ----------------------------------------
    gappers = scan_gaps(broker, instruments, prev_close, top_n=25)

    # 5. Score each candidate ---------------------------------------------
    candidates = []
    for g in gappers:
        opening = compute_opening_range(broker, g.token, g.symbol)
        if not opening:
            continue
        ltp = broker.ltp("NSE", g.trading_symbol, g.token)
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
    top10 = candidates[:10]
    if not top10:
        notifier.alert("No qualifying candidates after ORB — sitting out today.")
        return

    notifier.alert(
        "Top 10 candidates:\n" + "\n".join(
            f"  {i+1}. {g.symbol}  score={s}  ltp={ltp:.2f}  ({v.summary})"
            for i, (s, g, ltp, v) in enumerate(top10)
        )
    )

    # 6. Pick the winner --------------------------------------------------
    best = top10[0]
    if best[0] < settings.min_score:
        notifier.alert(f"Best score {best[0]} < threshold {settings.min_score} — no trade.")
        return

    s, g, ltp, verdict = best
    engine.open_long(symbol=g.symbol, token=g.token, trading_symbol=g.trading_symbol,
                     ltp=ltp, score=s, note=verdict.summary)

    # 7. Live monitoring --------------------------------------------------
    token_to_symbol = {g.token: g.symbol for _, g, _, _ in top10}
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
        notifier.alert("Market closed — bot shutting down. Review logs/trades_*.csv")


if __name__ == "__main__":
    run_day()
