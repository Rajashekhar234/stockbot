# Intraday Stock Trading Bot

Implements *Trading_Bot_Strategy_v2.docx* — an Indian intraday cash-equity discovery bot.
Universe = NSE F&O stocks (~180), price ₹100–₹3000, EQ series only.
Edge = Gap-up + Volume shocker + Opening-Range Breakout + Gemini news catalyst.

> The bot's #1 job is **stock discovery**. Buy/sell can be manual or automatic.

---

## 1. Setup

```powershell
cd C:\stockbot
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then open [.env](.env) and fill in your credentials when ready:

| Variable | How to get it |
|---|---|
| `ANGEL_API_KEY` | https://smartapi.angelbroking.com → My Apps → create Trading App |
| `ANGEL_CLIENT_CODE` | Your Angel One client/login id |
| `ANGEL_PASSWORD` | Your login password |
| `ANGEL_TOTP_SECRET` | When you enable TOTP on Angel One you'll see a Base32 secret — paste it here |
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey |

The bot starts in `TRADE_MODE=PAPER`. It will **never** place a real order until you set `TRADE_MODE=LIVE`.

---

## 2. Run

```powershell
# one-shot — waits for 09:30 IST, then runs the day
python main.py

# daemon mode — fires itself every weekday 08:55 IST
python main.py --schedule
```

Logs land in [logs/bot.log](logs/) and the day's trade ledger in `logs/trades_YYYYMMDD.csv`.

---

## 3. What the bot does (matches strategy doc)

| Time (IST) | Phase | File |
|---|---|---|
| 08:55 | Build universe (F&O ∩ EQ ∩ price band), GIFT-Nifty bias | [src/universe/fno_universe.py](src/universe/fno_universe.py), [src/premarket/gift_nifty.py](src/premarket/gift_nifty.py) |
| 09:15–09:30 | Record opening range (15-min H/L/V) | [src/scanner/orb.py](src/scanner/orb.py) |
| 09:30 | Gap scan → ORB-confirmed shortlist → Gemini news → score 0–100 | [src/premarket/gap_scanner.py](src/premarket/gap_scanner.py), [src/scanner/scorer.py](src/scanner/scorer.py), [src/ai/gemini_news.py](src/ai/gemini_news.py) |
| 09:30+ | Pick best ≥80 → BUY → live tick monitoring | [src/trade/engine.py](src/trade/engine.py), [src/stream/websocket_feed.py](src/stream/websocket_feed.py) |
| any time | Exit on -1% SL or +2.5% target, trail after +1.5% | [src/trade/engine.py](src/trade/engine.py) |
| 14:30 | Block any new entries | [src/orchestrator.py](src/orchestrator.py) |
| 15:00 | Force-exit any open position | [src/trade/engine.py](src/trade/engine.py) |

### Hard-coded safety rules

* Skip everything outside NSE `EQ` series (no T2T / BE)
* Skip if price < ₹100 or > ₹3000
* Skip if GIFT Nifty ≤ −200 pts (preserve capital day)
* Never invest > 80% of capital in one trade
* Never hold overnight — force exit at 15:00
* Never disable the −1% stop loss

---

## 4. Modes

| `TRADE_MODE` | Behaviour |
|---|---|
| `PAPER` *(default)* | All decisions logged, no orders placed |
| `ALERT_ONLY` | Sends BUY/SELL alerts (console + sound + Telegram if configured) — you act manually |
| `LIVE` | Calls `placeOrder` on Angel One. Use only after weeks of paper testing |

---

## 5. Project layout

```
config.py                 — env loader & constants
main.py                   — CLI entry / scheduler
src/
  broker/angel_client.py  — SmartAPI login, candles, orders, WS factory
  universe/fno_universe.py— F&O ∩ EQ universe builder
  premarket/
    gift_nifty.py         — GIFT Nifty bias
    gap_scanner.py        — gap %, top-25 movers
  scanner/
    orb.py                — 09:15–09:30 opening range
    volume.py             — volume multiplier vs 20-day avg
    scorer.py             — 0–100 composite score
  ai/gemini_news.py       — news fetch + Gemini sentiment
  stream/websocket_feed.py— SmartWebSocketV2 subscriber
  trade/engine.py         — entry, SL/target/trailing, force-EOD, ledger
  alerts/notifier.py      — console + beep + Telegram
  utils/                  — logger, IST clock
  orchestrator.py         — daily routine
logs/                     — bot.log + trades_YYYYMMDD.csv
data/cache/               — daily-cached scrip master + F&O list
```

---

## 6. Going to production

Deploy free on **Oracle Cloud Always-Free Ampere A1 VM** — step-by-step in [deploy/ORACLE_CLOUD.md](deploy/ORACLE_CLOUD.md).

Includes:
* systemd unit ([deploy/stockbot.service](deploy/stockbot.service))
* Telegram bot setup (BotFather + admin id whitelist)
* IST timezone setup
* `/pause` `/resume` `/stop` `/status` `/positions` commands

## 7. Position sizing

Two modes — set in `.env`:

| Setting | Behaviour |
|---|---|
| `TRADE_AMOUNT=30000` | Spend exactly ₹30k per trade. Qty = floor(30000 / ltp). Recommended. |
| `TRADE_AMOUNT=` (empty) | Use `CAPITAL * MAX_POSITION_PCT` instead. |
| `MAX_QTY=N` | Optional hard cap on shares. 0 = no cap. |

---

## 8. Testing checklist (do this in PAPER for 2 weeks)

- [ ] Bot starts at 08:55 IST without errors
- [ ] Universe size sanity (~120–180 names after price band)
- [ ] GIFT Nifty bias prints
- [ ] Top-10 candidates printed at 09:30
- [ ] Score column reasonable (top stock ≥ 80 on volatile days, < 80 on flat days)
- [ ] BUY alert fires (or correctly skipped)
- [ ] WebSocket ticks land in `bot.log`
- [ ] SL / Target / Force-EOD all log correctly in `trades_*.csv`
- [ ] Daily P&L reconciles vs manual broker statement
