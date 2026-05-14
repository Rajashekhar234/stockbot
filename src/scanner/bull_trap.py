"""
Bull-trap detector.

Watches the 09:15-09:30 ORB window. If a stock spiked sharply at open
(peak) and has since dropped >= 1.5 %, the early bullish move was a trap;
ORB-breakout entries get rejected for that symbol.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.logger import get_logger

log = get_logger("bull-trap")


@dataclass
class _State:
    peak: float = 0.0
    rejected: bool = False


@dataclass
class BullTrapDetector:
    drop_threshold_pct: float = 1.5
    _state: dict[str, _State] = field(default_factory=dict)

    def update(self, symbol: str, ltp: float) -> None:
        s = self._state.setdefault(symbol, _State())
        if ltp > s.peak:
            s.peak = ltp
            return
        if s.peak <= 0 or s.rejected:
            return
        drop = (s.peak - ltp) / s.peak * 100
        if drop >= self.drop_threshold_pct:
            s.rejected = True
            log.warning("BULL TRAP rejected %s — peak ₹%.2f → ₹%.2f (-%.2f%%)",
                        symbol, s.peak, ltp, drop)

    def is_rejected(self, symbol: str) -> bool:
        s = self._state.get(symbol)
        return bool(s and s.rejected)
