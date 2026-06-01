#!/usr/bin/env python3
"""
TVClient — drop-in replacement for FMPClient that sources OHLCV from a live
TradingView Desktop chart via the `tv` CLI (Chrome DevTools Protocol on :9222)
instead of the FMP REST API.

Why: the FMP free tier gates most symbols at the API level, so a real S&P 500
VCP scan is impossible. TradingView serves daily bars for any symbol with no
per-symbol or per-day request cap, so we route the screener's data layer through
it. The class mirrors FMPClient's public interface (get_quote,
get_historical_prices, get_batch_quotes, get_batch_historical, calculate_sma,
get_api_stats) so screen_vcp.py works unchanged once FMPClient is swapped out.

Data shape contract (matches FMPClient):
  - get_historical_prices -> {"symbol", "historical": [bar, ...]} NEWEST FIRST
  - each bar: {date, open, high, low, close, adjClose, volume}
  - get_quote -> {price, yearHigh, yearLow, avgVolume, volume, marketCap, name}
TradingView returns bars OLDEST first, so we reverse them.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# Repo root holds src/cli/index.js (the `tv` CLI entry point).
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
CLI = os.path.join(REPO_ROOT, "src", "cli", "index.js")

# Fast path: a fresh state/metrics/TICKER.json snapshot (written by
# scripts/collect_russell.js) serves the pre-filter quote without a chart switch.
# The full VCP/volume analysis still pulls live bars (the cache has no raw bar
# series). Stale (>2 days)/missing snapshots fall back to live. Disable with
# VCP_NO_CACHE=1.
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
try:
    import metrics_cache  # noqa: E402

    _CACHE_OK = os.environ.get("VCP_NO_CACHE") not in ("1", "true", "yes")
except ImportError:
    metrics_cache = None
    _CACHE_OK = False

# How many daily bars to pull per symbol. 400 ~= 18 months, comfortably covers
# the 200-day SMA (+22-day slope) and the 1-year (252d) relative-strength window.
BARS = 400
# Seconds to wait after switching symbol before the chart's bars are ready.
SETTLE = 2.0


class TVClient:
    def __init__(self, api_key: Optional[str] = None):
        # api_key accepted for interface parity with FMPClient; unused.
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

        # Trend Template needs a 200-day SMA; a stock with fewer daily bars
        # (recent IPO/spin-off) can't be Stage-2-evaluated. Skip it cleanly
        # instead of feeding short history into the calculators (which crash on
        # a None SMA). The screener treats an empty history as "skip symbol".
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

    # ------------------------------------------------------------- public API
    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        cache_key = f"hist_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fast path: fresh state/metrics/TICKER/ohlcv.json (no chart switch).
        # Require >=200 bars to mirror _fetch_bars' minimum-history skip.
        if _CACHE_OK:
            cb = metrics_cache.cached_ohlcv(symbol, min_bars=200)
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

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Synthesize a quote from the daily history (TradingView has no quote
        endpoint that mirrors FMP's fields; the screener only needs price,
        52-week high/low and average volume)."""
        cache_key = f"quote_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fast path: fresh metrics snapshot (skip the chart switch + bar pull).
        if _CACHE_OK:
            cq = metrics_cache.cached_quote(symbol)
            if cq:
                self.cache[cache_key] = cq
                return cq

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
        self.cache[cache_key] = quote
        return quote

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

    def get_batch_historical(self, symbols: list[str], days: int = 260) -> dict[str, list[dict]]:
        results = {}
        for sym in symbols:
            data = self.get_historical_prices(sym, days=days)
            if data and "historical" in data:
                results[sym] = data["historical"]
        return results

    def calculate_sma(self, prices: list[float], period: int) -> float:
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[:period]) / period

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

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": self.rate_limit_reached,
        }
