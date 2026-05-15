"""Fetch today's NSE pre-open and apply the bot's full selection funnel."""
from __future__ import annotations

import csv
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from config import settings
from src.universe.nse_client import NSEClient


def main() -> None:
    n = NSEClient()

    ish, desc = n.is_today_holiday()
    print(f"Holiday today? {ish}  {desc}")

    ban = n.fo_ban_list()
    print(f"F&O ban list: {sorted(ban) if ban else '(none / api throttled)'}")

    all_rows = n.pre_open("ALL")
    print(f"Total pre-open rows (ALL): {len(all_rows)}")

    eq_rows = [r for r in all_rows if r.series == "EQ"]
    print(f"EQ-only rows: {len(eq_rows)}")

    fo_raw = n.fno_securities()
    fo_syms = {(r if isinstance(r, str) else r.symbol) for r in fo_raw}
    print(f"F&O underlyings: {len(fo_syms)}")

    fo_rows = [r for r in eq_rows if r.symbol in fo_syms]
    print(f"EQ ∩ F&O: {len(fo_rows)}")

    band = [
        r
        for r in fo_rows
        if r.prev_close
        and settings.min_price <= r.prev_close <= settings.max_price
    ]
    print(f"After ₹{settings.min_price}-₹{settings.max_price} band: {len(band)}")

    band = [r for r in band if r.symbol not in ban]
    print(f"After ban filter: {len(band)}")

    # Long-only bot: positive gaps first, sorted descending
    band.sort(key=lambda r: (r.change_pct < 0, -r.change_pct))
    top = band[:10]

    out = pathlib.Path("data") / f"preopen_top_{datetime.now():%Y%m%d}.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "symbol", "prev_close", "open", "change_pct", "qty"])
        for i, r in enumerate(top, 1):
            qty = max(1, int((settings.capital * 0.8) // r.prev_close))
            w.writerow(
                [i, r.symbol, r.prev_close, r.open_price, round(r.change_pct, 2), qty]
            )

    print()
    print(f">>> TOP 10 (long-only bias) — saved {out}")
    print("-" * 78)
    print(f"{'#':<3}{'SYMBOL':<14}{'PREV':>10}{'OPEN':>10}{'GAP%':>8}   NOTE")
    print("-" * 78)
    for i, r in enumerate(top, 1):
        note = "GAP UP ✓" if r.change_pct > 0 else "GAP DOWN — skipped (long-only)"
        print(
            f"{i:<3}{r.symbol:<14}{r.prev_close:>10.2f}{r.open_price:>10.2f}"
            f"{r.change_pct:>+8.2f}   {note}"
        )

    print()
    positive = [r for r in top if r.change_pct > 0]
    if positive:
        pick = positive[0]
        qty = max(1, int((settings.capital * 0.8) // pick.prev_close))
        print(
            f">>> LIKELY PICK: {pick.symbol}  gap +{pick.change_pct:.2f}%  "
            f"qty {qty} @ ~₹{pick.open_price:.2f}"
        )
        print(
            f"    Final = depends on 09:30 ORB breakout + score ≥ {settings.min_score}"
            f" + Gemini news + GIFT bias."
        )
    else:
        print(">>> No positive gappers — bot would sit out today.")


if __name__ == "__main__":
    main()
