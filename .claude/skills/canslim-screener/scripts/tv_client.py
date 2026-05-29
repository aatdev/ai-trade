#!/usr/bin/env python3
"""
TVClient — hybrid drop-in replacement for FMPClient in the CANSLIM screener.

The CANSLIM components split cleanly by data type:
  - PRICE-based (N, S, L, M): 52-week high distance, up/down volume, relative
    strength vs ^GSPC, ^GSPC trend vs 50-day EMA. All derivable from daily bars.
  - FUNDAMENTAL (C, A, I): quarterly/annual earnings growth, institutional
    sponsorship. NOT available from chart bars.

So this client sources the PRICE methods (get_quote, get_historical_prices) from
a live TradingView Desktop chart via the `tv` CLI (CDP on :9222) — bypassing the
FMP free-tier per-symbol/day quota that makes a real universe scan impossible —
and DELEGATES the fundamental methods (get_profile, get_income_statement,
get_institutional_holders, calculate_ema) to an internal FMPClient.

Net effect: N/S/L/M run with no FMP price quota; the FMP key is only spent on
C/A/I fundamentals (~3 calls/stock instead of ~7), and ^GSPC/^VIX/52-week
history come free from the chart. screen_canslim.py is unchanged — screen_canslim_tv.py
swaps FMPClient for this class.

Data shape contract (matches canslim's FMPClient, which differs from vcp's):
  - get_quote -> list[dict]  (consumed as quote[0]); FMP fields: price, yearHigh,
    yearLow, volume, avgVolume, marketCap, symbol, name
  - get_historical_prices -> {"symbol", "historical": [bar, ...]} NEWEST FIRST
  - each bar: {date, open, high, low, close, adjClose, volume}
TradingView returns bars OLDEST first, so we reverse them.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from fmp_client import FMPClient

# Repo root holds src/cli/index.js (the `tv` CLI entry point).
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
CLI = os.path.join(REPO_ROOT, "src", "cli", "index.js")

# How many daily bars to pull per symbol. 400 ~= 18 months, comfortably covers
# the 50-day EMA, 90-day supply/demand window and the 1-year (252d) relative
# strength window the L component needs.
BARS = 400
# Seconds to wait after switching symbol before the chart's bars are ready.
SETTLE = 2.0


class TVClient:
    def __init__(self, api_key: Optional[str] = None):
        # C (quarterly earnings) and A (annual growth) now come from the
        # TradingView scanner via `tv fundamentals` — no FMP quota. The internal
        # FMP client is only kept for I (institutional holders), which the
        # scanner fundamentals set does not expose. The FMP key is now OPTIONAL:
        # with no key, fundamentals still flow from TradingView and I falls back
        # to the Finviz path in the calculator.
        try:
            self._fmp = FMPClient(api_key=api_key)
        except ValueError:
            self._fmp = None
            print(
                "  INFO: no FMP key — C/A from TradingView, I via Finviz fallback",
                file=sys.stderr,
            )
        self.cache: dict = {}
        self.api_calls_made = 0
        self.rate_limit_reached = False
        self._tf_set = False
        # Fail fast if TradingView/CLI is not reachable.
        if not os.path.exists(CLI):
            raise ValueError(f"tv CLI not found at {CLI}")

    # ------------------------------------------------------------------ CLI
    def _cli(self, *args: str, parse: bool = True):
        self.api_calls_made += 1
        try:
            out = subprocess.run(
                ["node", CLI, *args],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=40,
            )
        except subprocess.TimeoutExpired:
            print(f"  WARN: tv {' '.join(args)} timed out", file=sys.stderr)
            return None
        if out.returncode != 0:
            return None
        if not parse:
            return out.stdout
        try:
            return json.loads(out.stdout)
        except (json.JSONDecodeError, ValueError):
            return None

    def _fetch_bars(self, symbol: str) -> list[dict]:
        """Switch the chart to `symbol` on the daily timeframe and pull bars.

        Returns bars NEWEST FIRST in FMP-compatible dict form, or []."""
        self._cli("symbol", symbol, parse=False)
        if not self._tf_set:
            self._cli("timeframe", "D", parse=False)
            self._tf_set = True
        time.sleep(SETTLE)
        data = self._cli("ohlcv", "-n", str(BARS))

        # Chart may still be loading right after a symbol switch — retry once.
        if not data or not data.get("bars"):
            time.sleep(SETTLE * 1.5)
            data = self._cli("ohlcv", "-n", str(BARS))
        if not data or not data.get("bars"):
            return []

        # CANSLIM's L (52-week RS) and M (50-day EMA) need a year of history; a
        # stock with too few daily bars (recent IPO/spin-off) can't be scored.
        # Skip cleanly instead of feeding short history into the calculators.
        if len(data["bars"]) < 200:
            print(
                f"  SKIP {symbol}: only {len(data['bars'])} daily bars (<200)",
                file=sys.stderr,
            )
            return []

        raw = data["bars"]  # oldest first
        bars = []
        for b in raw:
            try:
                ts = int(b["time"])
                iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except (KeyError, ValueError, OSError):
                iso = ""
            close = b.get("close", 0)
            bars.append(
                {
                    "date": iso,
                    "open": b.get("open", 0),
                    "high": b.get("high", 0),
                    "low": b.get("low", 0),
                    "close": close,
                    "adjClose": close,
                    "volume": b.get("volume", 0) or 0,
                }
            )
        bars.reverse()  # newest first, matching FMP
        return bars

    # ----------------------------------------------------- PRICE (from TradingView)
    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        # `days` is ignored — we always pull BARS (>=400) and let the
        # calculators slice the window they need. Matches FMP's return shape.
        cache_key = f"hist_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        bars = self._fetch_bars(symbol)
        if not bars:
            self.cache[cache_key] = None
            return None
        result = {"symbol": symbol, "historical": bars}
        self.cache[cache_key] = result
        return result

    def get_quote(self, symbols: str) -> Optional[list[dict]]:
        """Synthesize a quote from the daily history. Returns a list[dict] to
        match canslim's FMPClient (consumed as quote[0]). Single symbol only —
        the screener never batches quote symbols through one call."""
        cache_key = f"quote_{symbols}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        hist = self.get_historical_prices(symbols)
        if not hist or not hist["historical"]:
            self.cache[cache_key] = None
            return None

        bars = hist["historical"]  # newest first
        year = bars[:252] if len(bars) >= 252 else bars
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in year]
        lows = [b["low"] for b in year if b["low"] > 0]
        vols = [b["volume"] for b in bars[:50]]

        quote = [
            {
                "symbol": symbols,
                "name": symbols,
                "price": closes[0] if closes else 0,
                "yearHigh": max(highs) if highs else 0,
                "yearLow": min(lows) if lows else 0,
                "avgVolume": (sum(vols) / len(vols)) if vols else 0,
                "volume": bars[0]["volume"] if bars else 0,
                "marketCap": 0,  # not available from chart bars
            }
        ]
        self.cache[cache_key] = quote
        return quote

    # ---------------------------------------- FUNDAMENTAL (TradingView scanner)
    def _fundamentals(self, symbol: str) -> Optional[dict]:
        """Fetch fundamentals for `symbol` from the TradingView scanner via the
        `tv fundamentals` CLI. Caches the parsed payload per symbol.

        Ensures the chart is on `symbol` first (get_quote switches + caches it),
        then reads the active chart so the bare ticker resolves to the right
        exchange. Returns the CLI payload dict, or None on failure."""
        cache_key = f"fund_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Put the chart on this symbol so `tv fundamentals` (no arg) reads it
        # with the correct exchange. get_quote is cached, so this is cheap.
        self.get_quote(symbol)
        data = self._cli("fundamentals", "--history")
        if not data or not data.get("success"):
            self.cache[cache_key] = None
            return None
        self.cache[cache_key] = data
        return data

    def get_profile(self, symbol: str) -> Optional[list[dict]]:
        """FMP-shaped profile [{companyName, sector, industry, mktCap, price}]
        built from scanner fundamentals. Falls back to FMP on failure."""
        data = self._fundamentals(symbol)
        if data:
            profile = data.get("profile", {})
            valuation = data.get("valuation", {})
            quote = self.get_quote(symbol)
            price = quote[0]["price"] if quote else None
            return [
                {
                    "symbol": symbol,
                    "companyName": data.get("name") or profile.get("description"),
                    "sector": profile.get("sector"),
                    "industry": profile.get("industry"),
                    "mktCap": valuation.get("market_cap_basic"),
                    "price": price,
                }
            ]
        return self._fmp.get_profile(symbol)

    def get_income_statement(
        self, symbol: str, period: str = "quarter", limit: int = 8
    ) -> Optional[list[dict]]:
        """FMP-shaped income statements (most recent first) built from the
        scanner's historical series. `date` is left None — the CANSLIM
        calculators use it only for error text, never for logic. Falls back to
        FMP on failure."""
        data = self._fundamentals(symbol)
        if data:
            hist = data.get("history", {})
            if period == "annual":
                rev = hist.get("total_revenue_fy_h", [])
                eps = hist.get("earnings_per_share_diluted_fy_h", [])
                ni = hist.get("net_income_fy_h", [])
            else:
                rev = hist.get("total_revenue_fq_h", [])
                eps = hist.get("earnings_per_share_diluted_fq_h", [])
                ni = hist.get("net_income_fq_h", [])
            n = min(limit, len(eps), len(rev))
            if n > 0:
                return [
                    {
                        "date": None,
                        "eps": eps[i],
                        "epsdiluted": eps[i],
                        "revenue": rev[i],
                        "netIncome": ni[i] if i < len(ni) else None,
                    }
                    for i in range(n)
                ]
        return self._fmp.get_income_statement(symbol, period=period, limit=limit)

    def get_institutional_holders(self, symbol: str) -> Optional[list[dict]]:
        # Not exposed by the scanner fundamentals — stays on FMP. Without a key
        # this returns None and the calculator's Finviz fallback handles I.
        if self._fmp is None:
            return None
        return self._fmp.get_institutional_holders(symbol)

    def calculate_ema(self, prices: list[float], period: int = 50) -> float:
        """Standard EMA (prices most-recent-first), computed locally so the M
        component needs no FMP key. Matches FMPClient.calculate_ema."""
        if not prices:
            return 0.0
        if len(prices) < period:
            return sum(prices) / len(prices)
        prices_reversed = prices[::-1]  # oldest first
        ema = sum(prices_reversed[:period]) / period  # seed with SMA
        k = 2 / (period + 1)
        for price in prices_reversed[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    # ----------------------------------------------------------------- utility
    def clear_cache(self):
        self.cache.clear()
        if self._fmp is not None:
            self._fmp.clear_cache()

    def get_api_stats(self) -> dict:
        fmp_stats = self._fmp.get_api_stats() if self._fmp is not None else {}
        return {
            "cache_entries": len(self.cache) + fmp_stats.get("cache_entries", 0),
            "tv_cli_calls": self.api_calls_made,
            "rate_limit_reached": self.rate_limit_reached
            or fmp_stats.get("rate_limit_reached", False),
        }
