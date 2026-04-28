#!/usr/bin/env python3
"""
FMP API Client for VCP Screener

Provides rate-limited access to Financial Modeling Prep API endpoints
for VCP (Volatility Contraction Pattern) screening.

Features:
- Rate limiting (0.3s between requests)
- Automatic retry on 429 errors
- Session caching for duplicate requests
- Batch quote support
- S&P 500 constituents fetching
"""

import os
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class FMPClient:
    """Client for Financial Modeling Prep API with rate limiting and caching"""

    BASE_URL = "https://financialmodelingprep.com/stable"
    RATE_LIMIT_DELAY = 0.3  # 300ms between requests

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required. Set FMP_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.session = requests.Session()
        self.session.headers.update({"apikey": self.api_key})
        self.cache = {}
        self.last_call_time = 0
        self.rate_limit_reached = False
        self.retry_count = 0
        self.max_retries = 1
        self.api_calls_made = 0

    def _rate_limited_get(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}

        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)

        try:
            response = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()
            self.api_calls_made += 1

            if response.status_code == 200:
                self.retry_count = 0
                return response.json()
            elif response.status_code == 429:
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    print("WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._rate_limited_get(url, params)
                else:
                    print("ERROR: Daily API rate limit reached.", file=sys.stderr)
                    self.rate_limit_reached = True
                    return None
            else:
                print(
                    f"ERROR: API request failed: {response.status_code} - {response.text[:200]}",
                    file=sys.stderr,
                )
                return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request exception: {e}", file=sys.stderr)
            return None

    def get_sp500_constituents(self) -> Optional[list[dict]]:
        """Fetch S&P 500 constituent list."""
        cache_key = "sp500_constituents"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/sp500-constituent"
        data = self._rate_limited_get(url)
        if data and isinstance(data, list):
            self.cache[cache_key] = data
            return data
        return None

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Fetch real-time quote data for a single symbol"""
        cache_key = f"quote_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/quote"
        data = self._rate_limited_get(url, {"symbol": symbol})
        if data and isinstance(data, list) and len(data) > 0:
            result = data[0]
            self.cache[cache_key] = result
            return result
        return None

    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        """Fetch historical daily OHLCV data.

        Returns dict with "historical" key (list of bars, newest first) for
        backward compatibility with screen_vcp.py.
        """
        import datetime

        cache_key = f"prices_{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        to_date = datetime.date.today()
        from_date = to_date - datetime.timedelta(days=days + 30)  # +30 buffer for weekends/holidays

        url = f"{self.BASE_URL}/historical-price-eod/full"
        params = {
            "symbol": symbol,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        }
        data = self._rate_limited_get(url, params)
        if data and isinstance(data, list) and len(data) > 0:
            # Wrap in legacy format; API returns newest-first already
            result = {"symbol": symbol, "historical": data}
            self.cache[cache_key] = result
            return result
        return None

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch quotes for a list of symbols, one at a time (batch requires premium)"""
        results = {}
        for sym in symbols:
            quote = self.get_quote(sym)
            if quote:
                results[sym] = quote
        return results

    def get_batch_historical(self, symbols: list[str], days: int = 260) -> dict[str, list[dict]]:
        """Fetch historical prices for multiple symbols"""
        results = {}
        for symbol in symbols:
            data = self.get_historical_prices(symbol, days=days)
            if data and "historical" in data:
                results[symbol] = data["historical"]
        return results

    def calculate_sma(self, prices: list[float], period: int) -> float:
        """Calculate Simple Moving Average from a list of prices (most recent first)"""
        if len(prices) < period:
            return sum(prices) / len(prices)
        return sum(prices[:period]) / period

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": self.rate_limit_reached,
        }
