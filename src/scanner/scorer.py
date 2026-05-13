"""
Composite stock-score (0-100) per strategy doc Section H.

Weights (sum = 100):
  Gap-up size           : 20
  Volume multiplier     : 20
  ORB breakout strength : 20
  Trend (above VWAP)    : 10
  News catalyst (Gemini): 20
  GIFT Nifty alignment  : 10
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreInputs:
    gap_pct: float = 0.0
    volume_x: float = 0.0
    orb_break_pct: float = 0.0   # (ltp - or_high)/or_high * 100
    above_vwap: bool = False
    news_sentiment: float = 0.0  # -1..+1 from Gemini
    gift_bullish: bool = False


def score(s: ScoreInputs) -> int:
    pts = 0.0

    # Gap up: 0% → 0pts, 1% → 10pts, ≥3% → 20pts
    pts += min(20, max(0, s.gap_pct) / 3 * 20)

    # Volume: 1x → 0, 3x → 10, ≥5x → 20
    pts += min(20, max(0, s.volume_x - 1) / 4 * 20)

    # ORB break: 0% → 0, 0.5% → 15, ≥1% → 20
    pts += min(20, max(0, s.orb_break_pct) / 1.0 * 20)

    if s.above_vwap:
        pts += 10

    # News catalyst: -1 → 0, 0 → 5, +1 → 20
    pts += max(0, (s.news_sentiment + 1) / 2 * 20)

    if s.gift_bullish:
        pts += 10

    return int(round(min(100, pts)))
