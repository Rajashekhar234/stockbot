"""
Hypothesis test (NO project changes):
  Universe = ALL NSE EQ + F&O underlyings
  Filter   = price >= 100 (no upper cap), exclude SM/BE/ST/SME series,
             require turnover >= 1 cr (kills micro-caps & illiquid names)
  Sort     = gap-up % desc
  Output   = top 15 picks
"""
from __future__ import annotations

import csv
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.universe.nse_client import NSEClient


def main() -> None:
    n = NSEClient()
    rows = n.pre_open("ALL")
    print(f"Total pre-open rows (ALL): {len(rows)}")

    # Step 1: liquid series only (EQ). Drop SM (SME), BE (T2T-ish), ST, BZ
    eq = [r for r in rows if r.series == "EQ"]
    print(f"After EQ-only filter:      {len(eq)}")

    # Step 2: price >= 100, no upper cap
    priced = [r for r in eq if r.prev_close and r.prev_close >= 100]
    print(f"After price >= Rs.100:     {len(priced)}")

    # Step 3: liquidity gate — pre-open value (qty * price) >= Rs.10 lakh
    #         (proxy for "people are actually trading this name today")
    def _value(r):
        return (r.final_qty or 0) * (r.open_price or r.prev_close or 0)

    liquid = [r for r in priced if _value(r) >= 10_00_000]  # 10 lakh
    print(f"After pre-open value>=10L: {len(liquid)}")

    # Step 4: gap-up bias (long-only)
    liquid.sort(key=lambda r: (r.change_pct < 0, -r.change_pct))
    top = liquid[:15]

    out = pathlib.Path("data") / f"hypothesis_top_{datetime.now():%Y%m%d}.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["rank", "symbol", "prev_close", "open", "change_pct", "preopen_value_lakh"]
        )
        for i, r in enumerate(top, 1):
            w.writerow(
                [
                    i,
                    r.symbol,
                    r.prev_close,
                    r.open_price,
                    round(r.change_pct, 2),
                    round(_value(r) / 1e5, 2),
                ]
            )

    print()
    print(f">>> TOP 15 (price>=100, pre-open value>=10L) — saved {out}")
    print("-" * 84)
    print(f"{'#':<3}{'SYMBOL':<18}{'PREV':>10}{'OPEN':>10}{'GAP%':>8}{'PO Lakh':>10}")
    print("-" * 84)
    for i, r in enumerate(top, 1):
        print(
            f"{i:<3}{r.symbol:<18}{r.prev_close:>10.2f}{r.open_price:>10.2f}"
            f"{r.change_pct:>+8.2f}{_value(r)/1e5:>10.2f}"
        )


if __name__ == "__main__":
    main()
