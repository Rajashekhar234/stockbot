"""
Thin wrapper around Angel One SmartAPI.

Handles:
  * Login with TOTP
  * Historical candles (for ORB / pre-market gap)
  * LTP quote
  * Order placement (MARKET / SL-M)
  * WebSocket V2 feed handover

If credentials are missing, methods raise so the caller can fall back
to PAPER mode safely.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pyotp

from config import settings
from src.utils.logger import get_logger

log = get_logger("angel")

try:
    from SmartApi import SmartConnect  # type: ignore
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore
    _HAS_SDK = True
except Exception as e:  # pragma: no cover
    SmartConnect = None  # type: ignore
    SmartWebSocketV2 = None  # type: ignore
    _HAS_SDK = False
    log.warning("smartapi-python not importable yet: %s", e)


class AngelClient:
    def __init__(self) -> None:
        self._smart: Any = None
        self._jwt: str = ""
        self._refresh: str = ""
        self._feed_token: str = ""

    # --------------------------------------------------------------- auth
    def _require_creds(self) -> None:
        missing = [k for k in ("angel_api_key", "angel_client_code",
                               "angel_password", "angel_totp_secret")
                   if not getattr(settings, k)]
        if missing:
            raise RuntimeError(f"Angel One credentials missing: {missing}")
        if not _HAS_SDK:
            raise RuntimeError("smartapi-python not installed")

    def login(self) -> None:
        self._require_creds()
        self._smart = SmartConnect(api_key=settings.angel_api_key)
        totp = pyotp.TOTP(settings.angel_totp_secret).now()
        data = self._smart.generateSession(
            settings.angel_client_code,
            settings.angel_password,
            totp,
        )
        if not data or not data.get("status"):
            raise RuntimeError(f"Angel login failed: {data}")
        self._jwt = data["data"]["jwtToken"]
        self._refresh = data["data"]["refreshToken"]
        self._feed_token = self._smart.getfeedToken()
        log.info("Angel One login OK as %s", settings.angel_client_code)

    # --------------------------------------------------------------- data
    def ltp(self, exchange: str, trading_symbol: str, token: str) -> float:
        r = self._smart.ltpData(exchange, trading_symbol, token)
        return float(r["data"]["ltp"])

    def candles(self, token: str, interval: str, days_back: int = 5,
                exchange: str = "NSE") -> list[list]:
        """interval: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, ONE_DAY ..."""
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=days_back)
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        }
        return self._smart.getCandleData(params).get("data", [])

    # --------------------------------------------------------------- orders
    def place_market_buy(self, trading_symbol: str, token: str, qty: int,
                         product: str = "INTRADAY") -> str:
        order = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": token,
            "transactiontype": "BUY",
            "exchange": "NSE",
            "ordertype": "MARKET",
            "producttype": product,
            "duration": "DAY",
            "quantity": qty,
        }
        oid = self._smart.placeOrder(order)
        log.info("MARKET BUY %s x%d → orderId=%s", trading_symbol, qty, oid)
        return oid

    def place_market_sell(self, trading_symbol: str, token: str, qty: int,
                          product: str = "INTRADAY") -> str:
        order = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": token,
            "transactiontype": "SELL",
            "exchange": "NSE",
            "ordertype": "MARKET",
            "producttype": product,
            "duration": "DAY",
            "quantity": qty,
        }
        oid = self._smart.placeOrder(order)
        log.info("MARKET SELL %s x%d → orderId=%s", trading_symbol, qty, oid)
        return oid

    # --------------------------------------------------------------- ws
    def make_ws(self) -> Any:
        if not _HAS_SDK:
            raise RuntimeError("smartapi-python not installed")
        return SmartWebSocketV2(
            auth_token=self._jwt,
            api_key=settings.angel_api_key,
            client_code=settings.angel_client_code,
            feed_token=self._feed_token,
        )

    @property
    def feed_token(self) -> str:
        return self._feed_token
