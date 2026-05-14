"""
NSE India website client.

NSE blocks bare requests. Two-step pattern:
  1. Hit the homepage so cookies (`nseappid`, `bm_sv`, etc.) get set.
  2. Call the JSON APIs with those cookies and a real browser User-Agent.

Endpoints we use:
  * Pre-open market data (per index)  → /api/market-data-pre-open?key=<INDEX>
  * F&O securities list                → /api/equity-stockIndices?index=SECURITIES%20IN%20F%26O
  * Index constituents                 → /api/equity-stockIndices?index=NIFTY%2050  (etc.)

Index keys for pre-open API:
  ALL        — every pre-open quote (~2000 stocks)
  NIFTY      — NIFTY 50
  NIFTYBANK  — Bank Nifty
  FO         — F&O underlyings only
  OTHERS     — non-F&O stocks
  SME        — SME segment
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from config import CACHE_DIR
from src.utils.logger import get_logger

log = get_logger("nse")

_BASE = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{_BASE}/",
    "Connection": "keep-alive",
}


@dataclass
class PreOpenRow:
    symbol: str             # e.g. RELIANCE
    series: str             # EQ / BE / SM ...
    prev_close: float
    open_price: float       # iep — indicative equilibrium price
    change_pct: float       # gap %
    final_qty: int
    total_turnover: float


class NSEClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self._warmed = False

    # ------------------------------------------------------------- session
    def _warm(self) -> None:
        if self._warmed:
            return
        try:
            # Hit homepage and the pre-open page so all cookies get planted
            self.session.get(_BASE, timeout=15)
            self.session.get(f"{_BASE}/market-data/pre-open-market-cm-and-emerge-market", timeout=15)
            self._warmed = True
            log.info("NSE session warmed (cookies=%d)", len(self.session.cookies))
        except Exception as e:
            log.warning("NSE warm-up failed: %s", e)

    def _get_json(self, path: str) -> dict | None:
        self._warm()
        url = f"{_BASE}{path}"
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=20)
                if r.status_code == 200 and r.text.strip().startswith(("{", "[")):
                    return r.json()
                # cookies may have expired; force re-warm
                self._warmed = False
                self._warm()
            except Exception as e:
                log.debug("NSE GET %s try %d failed: %s", path, attempt + 1, e)
        log.warning("NSE GET %s failed after retries", path)
        return None

    # ------------------------------------------------------------- public
    def pre_open(self, key: str = "FO") -> list[PreOpenRow]:
        """Returns pre-open snapshot for the given index key.

        Cached daily under data/cache/.
        """
        cache = CACHE_DIR / f"{date.today():%Y-%m-%d}_preopen_{key}.json"
        if cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
        else:
            data = self._get_json(f"/api/market-data-pre-open?key={key}")
            if data:
                cache.write_text(json.dumps(data), encoding="utf-8")

        if not data:
            return []

        rows: list[PreOpenRow] = []
        for item in data.get("data", []):
            md = item.get("metadata", {}) or {}
            det = item.get("detail", {}).get("preOpenMarket", {}) or {}
            sym = (md.get("symbol") or "").upper()
            if not sym or sym in {"NIFTY", "NIFTY50", "NIFTYBANK"}:
                continue
            try:
                rows.append(PreOpenRow(
                    symbol=sym,
                    series=(det.get("Series") or md.get("series") or "EQ").strip(),
                    prev_close=float(md.get("previousClose") or 0),
                    open_price=float(md.get("lastPrice") or det.get("IEP") or 0),
                    change_pct=float(md.get("pChange") or 0),
                    final_qty=int(det.get("finalQuantity") or 0),
                    total_turnover=float(det.get("totalTurnover") or 0),
                ))
            except (TypeError, ValueError):
                continue
        log.info("Pre-open '%s': %d rows", key, len(rows))
        return rows

    def fno_securities(self) -> list[str]:
        """Returns the list of NSE underlyings that have F&O contracts."""
        data = self._get_json("/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O")
        if not data:
            return []
        out = []
        for it in data.get("data", []):
            sym = (it.get("symbol") or "").upper()
            if sym and sym not in {"NIFTY 50", "NIFTY BANK", "NIFTY FIN SERVICE"}:
                out.append(sym)
        log.info("F&O securities from NSE: %d", len(out))
        return out

    def fo_ban_list(self) -> set[str]:
        """Stocks currently in F&O ban period — never trade these intraday."""
        data = self._get_json("/api/fo-ban-list")
        if not data:
            return set()
        banned = {(it.get("tradingSymbol") or it.get("symbol") or "").upper()
                  for it in data.get("data", [])}
        banned.discard("")
        if banned:
            log.warning("F&O ban list today: %d stocks → %s",
                        len(banned), sorted(banned))
        return banned

    def is_today_holiday(self) -> tuple[bool, str]:
        """Returns (True, description) if today is an NSE Capital Markets holiday."""
        from datetime import datetime
        today = datetime.now().strftime("%d-%b-%Y").upper()
        cache = CACHE_DIR / f"{date.today():%Y}_holidays.json"

        data = None
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                data = None
        if not data:
            data = self._get_json("/api/holiday-master?type=trading")
            if data:
                cache.write_text(json.dumps(data), encoding="utf-8")

        if not data:
            return False, ""
        for h in data.get("CM", []):
            if today in (h.get("tradingDate") or "").upper():
                return True, h.get("description", "Holiday")
        return False, ""
