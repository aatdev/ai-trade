#!/usr/bin/env python3
"""
Reader for the per-ticker metrics cache written by scripts/collect_russell.js.

Skills use this as a fast path: a fresh state/metrics/TICKER.json snapshot
serves quote, fundamentals, indicators and price stats without driving the live
chart. Past STALE_DAYS the snapshot is considered stale and callers should fall
back to a live fetch.

The two `cached_*` helpers below return data already shaped like the FMP/scanner
payloads the screeners' tv_client expects, so wiring is a one-line cache check.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

# scripts/lib → repo root is two levels up.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
METRICS_DIR = os.path.join(_REPO_ROOT, "state", "metrics")

STALE_DAYS = 2


def _safe_name(ticker: str) -> str:
    """Filesystem-safe token, matching metrics_store.js safeToken()."""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in ticker)


def ticker_dir(ticker: str) -> str:
    return os.path.join(METRICS_DIR, _safe_name(ticker))


def metrics_path(ticker: str) -> str:
    return os.path.join(ticker_dir(ticker), "metrics.json")


def ohlcv_path(ticker: str) -> str:
    return os.path.join(ticker_dir(ticker), "ohlcv.json")


def _read_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_metrics(ticker: str) -> Optional[dict]:
    """Load the raw metrics snapshot, or None if missing/unparseable."""
    return _read_json(metrics_path(ticker))


def read_ohlcv(ticker: str) -> Optional[dict]:
    """Load the raw OHLCV doc { ticker, collected_at, as_of_date, count, bars }."""
    return _read_json(ohlcv_path(ticker))


def age_days(metrics: Optional[dict]) -> float:
    """Age of the snapshot in days; inf if missing/invalid."""
    if not metrics or "collected_at" not in metrics:
        return float("inf")
    try:
        ts = datetime.fromisoformat(metrics["collected_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


def is_fresh(metrics: Optional[dict], stale_days: float = STALE_DAYS) -> bool:
    """True when the snapshot exists and is younger than `stale_days`."""
    return age_days(metrics) <= stale_days


def fresh_metrics(ticker: str, stale_days: float = STALE_DAYS) -> Optional[dict]:
    """Return the snapshot only if present AND fresh, else None."""
    m = read_metrics(ticker)
    return m if (m and is_fresh(m, stale_days)) else None


# ─── FMP-shaped projections (drop-in for tv_client) ──────────────────────────


def cached_quote(ticker: str, stale_days: float = STALE_DAYS) -> Optional[dict]:
    """FMP-shaped quote dict from a fresh snapshot, else None.

    Fields match tv_client.get_quote: price, yearHigh, yearLow, avgVolume,
    volume, marketCap, symbol, name. marketCap comes from cached fundamentals
    (unavailable from bare chart bars), so the cache is strictly richer here.
    """
    m = fresh_metrics(ticker, stale_days)
    if not m:
        return None
    price = m.get("price") or {}
    quote = m.get("quote") or {}
    fund = m.get("fundamentals") or {}
    market_cap = (fund.get("valuation") or {}).get("market_cap_basic", 0)
    return {
        "symbol": ticker,
        "name": m.get("name", ticker),
        "price": price.get("last_close") or quote.get("last") or 0,
        "yearHigh": price.get("year_high") or 0,
        "yearLow": price.get("year_low") or 0,
        "avgVolume": price.get("avg_volume_50d") or 0,
        "volume": quote.get("volume") or 0,
        "marketCap": market_cap or 0,
    }


def cached_fundamentals(ticker: str, stale_days: float = STALE_DAYS) -> Optional[dict]:
    """Scanner-shaped fundamentals payload from a fresh snapshot, else None.

    Mirrors the `tv fundamentals --history` CLI result the canslim tv_client
    consumes (success flag + name + field groups + history)."""
    m = fresh_metrics(ticker, stale_days)
    if not m or not m.get("fundamentals"):
        return None
    out = {"success": True, "symbol": ticker, "name": m.get("name", ticker)}
    out.update(m["fundamentals"])
    return out


def cached_indicators(ticker: str, stale_days: float = STALE_DAYS) -> Optional[dict]:
    """Latest indicator block (ema/sma/rsi/macd/stoch/bb/atr/returns), else None."""
    m = fresh_metrics(ticker, stale_days)
    return m.get("indicators") if m else None


def cached_ohlcv(
    ticker: str, min_bars: int = 1, stale_days: float = STALE_DAYS
) -> Optional[list]:
    """FMP-shaped daily bars from a fresh OHLCV file, NEWEST-FIRST, else None.

    Each bar: {date, open, high, low, close, adjClose, volume} — matches what
    tv_client.get_historical_prices returns, so it's a drop-in for the live
    chart pull. Returns None when the file is missing, stale, or shorter than
    `min_bars` (so the caller falls back to a live fetch that may reach further
    back, e.g. a recent IPO with sparse cache history)."""
    doc = read_ohlcv(ticker)
    if not doc or not doc.get("bars"):
        return None
    if not is_fresh(doc, stale_days):  # ohlcv.json carries its own collected_at
        return None
    bars = doc["bars"]  # stored OLDEST-FIRST
    if len(bars) < min_bars:
        return None
    out = []
    for b in reversed(bars):  # → NEWEST-FIRST
        close = b.get("close", 0)
        out.append(
            {
                "date": b.get("date", ""),
                "open": b.get("open", 0),
                "high": b.get("high", 0),
                "low": b.get("low", 0),
                "close": close,
                "adjClose": close,
                "volume": b.get("volume", 0) or 0,
            }
        )
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python metrics_cache.py <TICKER>", file=sys.stderr)
        sys.exit(2)
    t = sys.argv[1]
    snap = read_metrics(t)
    print(
        json.dumps(
            {
                "found": snap is not None,
                "fresh": is_fresh(snap),
                "age_days": None if snap is None else round(age_days(snap), 2),
                "stale_days": STALE_DAYS,
                "metrics": snap,
            },
            indent=2,
        )
    )
    sys.exit(0 if is_fresh(snap) else 3)
