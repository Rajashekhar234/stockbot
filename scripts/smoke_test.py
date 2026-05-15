"""Smoke test of new BROAD universe settings."""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from config import settings, PRE_OPEN_FETCH
from src.premarket.gap_scanner import fetch_pre_open_rows, scan_gaps
from src.universe.fno_universe import build_universe

print("Mode      :", settings.universe_mode)
print("Price     :", settings.min_price, "-", settings.max_price)
print("Min PO val:", f"Rs.{settings.min_preopen_value:,.0f}")
print("Top N     :", settings.max_candidates)
print("Fetch time:", PRE_OPEN_FETCH, "IST")
print()

t0 = time.time()
inst = build_universe()
print(f"Universe : {len(inst)} instruments  ({time.time()-t0:.1f}s)")

t0 = time.time()
rows = fetch_pre_open_rows()
print(f"Pre-open : {len(rows)} rows         ({time.time()-t0:.1f}s)")

top = scan_gaps(inst, rows)
print()
print("=== TOP 25 BOT WILL MONITOR ===")
print(f"{'#':<3}{'SYMBOL':<16}{'PREV':>10}{'OPEN':>10}{'GAP%':>8}{'PO Lakh':>10}")
for i, r in enumerate(top, 1):
    print(
        f"{i:<3}{r.symbol:<16}{r.prev_close:>10.2f}{r.open_price:>10.2f}"
        f"{r.gap_pct:>+8.2f}{r.pre_open_turnover/1e5:>10.2f}"
    )
