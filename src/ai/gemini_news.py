"""
Gemini-powered news catalyst & sentiment for a stock.

For each candidate symbol we:
  1. Pull the latest 5 headlines from Google News RSS.
  2. Send them to Gemini with a structured prompt.
  3. Receive {sentiment: -1..+1, catalyst: bool, summary: str}.

Falls back to neutral if API key missing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import requests

from config import settings
from src.utils.logger import get_logger

log = get_logger("gemini")

try:
    import google.generativeai as genai
    _HAS_GENAI = True
except Exception:
    genai = None  # type: ignore
    _HAS_GENAI = False


@dataclass
class NewsVerdict:
    sentiment: float = 0.0       # -1 .. +1
    catalyst: bool = False
    summary: str = ""


_NEWS_RSS = "https://news.google.com/rss/search?q={q}+stock+nse&hl=en-IN&gl=IN&ceid=IN:en"


def _fetch_headlines(symbol: str, limit: int = 5) -> list[str]:
    try:
        r = requests.get(_NEWS_RSS.format(q=quote_plus(symbol)), timeout=10)
        r.raise_for_status()
        titles = re.findall(r"<title>(.*?)</title>", r.text, flags=re.DOTALL)
        # First title is the feed name itself
        return [re.sub(r"<.*?>", "", t).strip() for t in titles[1: limit + 1]]
    except Exception as e:
        log.debug("news fetch failed for %s: %s", symbol, e)
        return []


_PROMPT = """You are a stock-news analyst for Indian intraday traders.

Stock: {symbol}
Recent headlines:
{headlines}

Reply ONLY with compact JSON:
{{"sentiment": <float -1..1>, "catalyst": <true|false>,
  "summary": "<<=20 words>"}}

`catalyst` = true only if the news is a real, fresh, material event
(earnings beat/miss, contract win, regulatory action, M&A, guidance change).
"""


def analyze(symbol: str) -> NewsVerdict:
    if not settings.gemini_api_key or not _HAS_GENAI:
        return NewsVerdict()

    headlines = _fetch_headlines(symbol)
    if not headlines:
        return NewsVerdict(summary="no news")

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        prompt = _PROMPT.format(symbol=symbol,
                                headlines="\n".join(f"- {h}" for h in headlines))
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return NewsVerdict(summary=text[:80])
        data = json.loads(m.group(0))
        return NewsVerdict(
            sentiment=float(data.get("sentiment", 0)),
            catalyst=bool(data.get("catalyst", False)),
            summary=str(data.get("summary", ""))[:200],
        )
    except Exception as e:
        log.warning("Gemini analysis failed for %s: %s", symbol, e)
        return NewsVerdict()
