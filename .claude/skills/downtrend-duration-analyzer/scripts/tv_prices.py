#!/usr/bin/env python3
"""
TradingView-backed price fetcher for the downtrend analyzer.

`fetch_historical_prices_tv` is a drop-in replacement for analyze_downtrends's
module-level `fetch_historical_prices(api_key, symbol, from_date, to_date)`: it
returns the same pandas DataFrame (columns date/open/high/low/close/volume,
sorted oldest-first, `date` as datetime), but sources daily bars from a live
TradingView Desktop chart via the `tv` CLI (CDP on :9222) instead of the FMP
historical-price endpoint.

Why: the per-symbol historical fetch is the call that burns the FMP free-tier
quota when scanning a large universe. The stock universe + market-cap list
(fetch_stock_list) still comes from FMP — the chart can't provide sector/market
cap — but that is a single cheap call.

TradingView returns bars oldest-first with epoch `time`; we map them to FMP's
column shape and filter to [from_date, to_date].
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import pandas as pd

# Repo root holds src/cli/index.js (the `tv` CLI entry point).
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
CLI = os.path.join(REPO_ROOT, "src", "cli", "index.js")

# Seconds to wait after switching symbol before the chart's bars are ready.
SETTLE = 2.0
# Hard ceiling on bars per request. The `tv ohlcv` CLI caps at 500 bars AND its
# piped stdout truncates at 64KB (~430 bars of JSON), so 400 is the largest
# value that returns valid, complete JSON. ~400 daily bars ≈ 18 months — that is
# the practical history window of the TradingView path, regardless of
# --lookback-years.
MAX_BARS = 400

_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
_tf_set = False  # set the daily timeframe only once per process


def _cli(*args: str, parse: bool = True):
    try:
        out = subprocess.run(
            ["node", CLI, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
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


def _bars_needed(from_date: str, to_date: str) -> int:
    """Estimate daily bars to cover [from_date, to_date] with headroom.

    ~252 trading days per calendar year (~0.69 of calendar days); add a buffer
    so peak/trough windows at the edges have context. Clamped to a sane range."""
    try:
        span = (datetime.strptime(to_date, "%Y-%m-%d") - datetime.strptime(from_date, "%Y-%m-%d")).days
    except ValueError:
        span = 365 * 5
    return max(250, min(int(span * 0.72) + 60, MAX_BARS))


def fetch_historical_prices_tv(symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
    """Daily OHLCV from the live TradingView chart, FMP-compatible DataFrame."""
    global _tf_set
    if not os.path.exists(CLI):
        print(f"ERROR: tv CLI not found at {CLI}", file=sys.stderr)
        return pd.DataFrame()

    _cli("symbol", symbol, parse=False)
    if not _tf_set:
        _cli("timeframe", "D", parse=False)
        _tf_set = True
    time.sleep(SETTLE)

    n = _bars_needed(from_date, to_date)
    data = _cli("ohlcv", "-n", str(n))
    # Chart may still be loading right after a symbol switch — retry once.
    if not data or not data.get("bars"):
        time.sleep(SETTLE * 1.5)
        data = _cli("ohlcv", "-n", str(n))
    if not data or not data.get("bars"):
        print(f"Error fetching prices for {symbol}: no bars from TradingView", file=sys.stderr)
        return pd.DataFrame()

    rows = []
    for b in data["bars"]:  # oldest first
        try:
            iso = datetime.fromtimestamp(int(b["time"]), tz=timezone.utc).strftime("%Y-%m-%d")
        except (KeyError, ValueError, OSError):
            continue
        rows.append(
            {
                "date": iso,
                "open": b.get("open", 0),
                "high": b.get("high", 0),
                "low": b.get("low", 0),
                "close": b.get("close", 0),
                "volume": b.get("volume", 0) or 0,
            }
        )
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    # Clip to the requested window (mirrors FMP's from/to filtering).
    mask = (df["date"] >= pd.to_datetime(from_date)) & (df["date"] <= pd.to_datetime(to_date))
    df = df[mask].sort_values("date").reset_index(drop=True)
    return df[_COLUMNS]
