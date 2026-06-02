#!/usr/bin/env python3
"""
TVClient (base) — reusable drop-in replacement for FMPClient that sources daily
OHLCV from a live TradingView Desktop chart via the `tv` CLI (Chrome DevTools
Protocol on :9222) instead of the FMP REST API.

Why this exists: the FMP free tier gates most symbols at the API level, so a real
S&P 500 / Russell scan is impossible. TradingView serves daily bars for any
symbol with no per-symbol or per-day request cap, so screeners route their data
layer through it. This base owns the PRICE layer — CLI plumbing, bar fetching,
the metrics-cache fast path, and FMP-shaped get_quote / get_historical_prices —
and is shared by every skill that needs chart-sourced prices:

  - vcp-screener   (quote as dict, no index remap)            -> VCP_NO_CACHE
  - canslim-screener (quote as list + fundamentals subclass)  -> CANSLIM_NO_CACHE
  - ftd-detector   (quote as list, ^GSPC -> SP:SPX remap)     -> FTD_NO_CACHE

Each skill keeps a thin `tv_client.py` subclass that configures the knobs and
(for CANSLIM) layers fundamentals on top. To stay reusable this module imports
NOTHING skill-specific — fundamentals/FMP delegation live in the subclasses.

Configuration knobs (constructor kwargs):
  - quote_as_list   : get_quote returns [dict] (FMP style) vs a bare dict.
  - index_remap     : {fmp_ticker: tv_symbol} applied before the chart switch;
                      remapped symbols also bypass the per-ticker metrics cache
                      (indices are not collected into state/metrics).
  - cache_disable_env : env var that turns the metrics-cache fast path off.
  - min_bars / bars / settle : history floor, bars to pull, post-switch settle.

Data shape contract (matches FMPClient):
  - get_historical_prices -> {"symbol", "historical": [bar, ...]} NEWEST FIRST
  - each bar: {date, open, high, low, close, adjClose, volume}
  - get_quote -> {price, yearHigh, yearLow, avgVolume, volume, marketCap, name}
                 (or [that dict] when quote_as_list=True)
TradingView returns bars OLDEST first, so we reverse them.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# Repo root holds src/cli/index.js (the `tv` CLI entry point). This file lives
# at scripts/lib/, so the repo root is two levels up.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLI = os.path.join(REPO_ROOT, "src", "cli", "index.js")

# Fast path: a fresh state/metrics/TICKER snapshot (written by
# scripts/collect_russell.js) serves the quote without a chart switch. Stale
# (>2 days) / missing snapshots transparently fall back to the live chart.
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
try:
    import metrics_cache  # noqa: E402
except ImportError:
    metrics_cache = None

# Defaults. 400 daily bars ~= 18 months — comfortably covers a 200-day SMA
# (+slope) and the 1-year (252d) relative-strength window every screener needs.
BARS = 400
# Seconds to wait after switching symbol before the chart's bars are ready.
SETTLE = 2.0
# Trend/RS calculators need a year of history; a stock with fewer daily bars
# (recent IPO/spin-off) can't be evaluated and is skipped cleanly.
MIN_BARS = 200


def _truthy_env(name: str) -> bool:
    return os.environ.get(name) in ("1", "true", "yes")


class TVClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        quote_as_list: bool = False,
        index_remap: Optional[dict] = None,
        cache_disable_env: str = "TV_NO_CACHE",
        min_bars: int = MIN_BARS,
        bars: int = BARS,
        settle: float = SETTLE,
    ):
        # api_key accepted for interface parity with FMPClient; the price layer
        # never uses it (TradingView needs no key). Subclasses that delegate
        # fundamentals to FMP consume it themselves.
        self.quote_as_list = quote_as_list
        self.index_remap = index_remap or {}
        self.min_bars = min_bars
        self.bars = bars
        self.settle = settle
        self._cache_ok = metrics_cache is not None and not _truthy_env(cache_disable_env)

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

        Applies index_remap before the switch (e.g. ^GSPC -> SP:SPX). Returns
        bars NEWEST FIRST in FMP-compatible dict form, or []."""
        tv_symbol = self.index_remap.get(symbol, symbol)
        self._cli("symbol", tv_symbol, parse=False)
        if not self._tf_set:
            self._cli("timeframe", "D", parse=False)
            self._tf_set = True
        time.sleep(self.settle)
        data = self._cli("ohlcv", "-n", str(self.bars))

        # Chart may still be loading right after a symbol switch — retry once.
        if not data or not data.get("bars"):
            time.sleep(self.settle * 1.5)
            data = self._cli("ohlcv", "-n", str(self.bars))
        if not data or not data.get("bars"):
            return []

        # Skip too-short histories cleanly instead of feeding them into the
        # calculators (which crash on a None SMA). An empty history reads as
        # "skip symbol" to every screener.
        if len(data["bars"]) < self.min_bars:
            print(
                f"  SKIP {symbol}: only {len(data['bars'])} daily bars (<{self.min_bars})",
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

    # ------------------------------------------------------------- public API
    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        # `days` is ignored — we always pull self.bars and let the calculators
        # slice the window they need. Matches FMP's return shape.
        cache_key = f"hist_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fast path: fresh state/metrics/TICKER/ohlcv.json (no chart switch).
        # Require >=min_bars to mirror _fetch_bars; remapped index symbols are
        # not collected, so skip the cache for them and go live.
        if self._cache_ok and symbol not in self.index_remap:
            cb = metrics_cache.cached_ohlcv(symbol, min_bars=self.min_bars)
            if cb:
                result = {"symbol": symbol, "historical": cb}
                self.cache[cache_key] = result
                return result

        bars = self._fetch_bars(symbol)
        if not bars:
            self.cache[cache_key] = None
            return None
        result = {"symbol": symbol, "historical": bars}
        self.cache[cache_key] = result
        return result

    def get_quote(self, symbol: str):
        """Synthesize a quote from the daily history (TradingView has no quote
        endpoint mirroring FMP's fields; screeners only need price, 52-week
        high/low and average volume). Single symbol only — screeners never batch
        symbols through one quote call. Returns [dict] when quote_as_list, else
        a bare dict, to match the consuming FMPClient's shape."""
        cache_key = f"quote_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fast path: fresh metrics snapshot (skip the chart switch + bar pull).
        if self._cache_ok and symbol not in self.index_remap:
            cq = metrics_cache.cached_quote(symbol)
            if cq:
                result = [cq] if self.quote_as_list else cq
                self.cache[cache_key] = result
                return result

        hist = self.get_historical_prices(symbol)
        if not hist or not hist["historical"]:
            self.cache[cache_key] = None
            return None

        bars = hist["historical"]  # newest first
        year = bars[:252] if len(bars) >= 252 else bars
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in year]
        lows = [b["low"] for b in year if b["low"] > 0]
        vols = [b["volume"] for b in bars[:50]]

        quote = {
            "symbol": symbol,
            "name": symbol,
            "price": closes[0] if closes else 0,
            "yearHigh": max(highs) if highs else 0,
            "yearLow": min(lows) if lows else 0,
            "avgVolume": (sum(vols) / len(vols)) if vols else 0,
            "volume": bars[0]["volume"] if bars else 0,
            "marketCap": 0,  # not available from chart bars
        }
        result = [quote] if self.quote_as_list else quote
        self.cache[cache_key] = result
        return result

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        results = {}
        total = len(symbols)
        for i, sym in enumerate(symbols):
            if (i + 1) % 10 == 0 or i == total - 1:
                print(f"    Progress: {i + 1}/{total}", flush=True)
            q = self.get_quote(sym)
            if q:
                results[sym] = q
        return results

    def get_batch_historical(
        self, symbols: list[str], days: int = 260
    ) -> dict[str, list[dict]]:
        results = {}
        for sym in symbols:
            data = self.get_historical_prices(sym, days=days)
            if data and "historical" in data:
                results[sym] = data["historical"]
        return results

    def calculate_sma(self, prices: list[float], period: int) -> float:
        """Simple Moving Average (prices most-recent-first)."""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[:period]) / period

    def calculate_ema(self, prices: list[float], period: int = 50) -> float:
        """Exponential Moving Average (prices most-recent-first), computed
        locally so no FMP key is needed. Matches FMPClient.calculate_ema."""
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

    def get_sp500_constituents(self) -> Optional[list[dict]]:
        """Return S&P 500 constituents from the local state/sp500.csv snapshot.

        Mirrors FMPClient.get_sp500_constituents (which hits the FMP REST API).
        FMP's free tier gates that endpoint, so we read the same Wikipedia-derived
        CSV that scripts/collect_russell.js walks. Returns [{symbol, name, sector}].
        Symbols keep their dotted form (BRK.B) — matches the metrics cache dirs.
        """
        cache_key = "sp500_constituents"
        if cache_key in self.cache:
            return self.cache[cache_key]

        csv_path = os.path.join(REPO_ROOT, "state", "sp500.csv")
        if not os.path.exists(csv_path):
            print(f"  WARN: {csv_path} not found", file=sys.stderr)
            return None

        import csv as _csv

        constituents = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                sym = (row.get("Symbol") or "").strip()
                if not sym:
                    continue
                constituents.append(
                    {
                        "symbol": sym,
                        "name": (row.get("Security") or sym).strip(),
                        "sector": (row.get("GICS Sector") or "Unknown").strip(),
                    }
                )
        if not constituents:
            return None
        self.cache[cache_key] = constituents
        return constituents

    # ----------------------------------------------------------------- utility
    def clear_cache(self):
        self.cache.clear()

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": self.rate_limit_reached,
        }
