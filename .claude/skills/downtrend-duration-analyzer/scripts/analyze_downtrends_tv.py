#!/usr/bin/env python3
"""
Run the downtrend-duration analyzer with price history from live TradingView.

Monkeypatches analyze_downtrends.fetch_historical_prices with a TradingView-backed
fetcher (daily bars via the `tv` CLI / CDP on :9222). The stock universe and
market-cap classification still come from FMP (fetch_stock_list) — the chart
can't provide sector/market cap — but that is a single cheap call, whereas the
per-symbol price history (previously the bulk of the FMP quota) is now free.

All CLI flags of analyze_downtrends.py are accepted verbatim (--sector,
--lookback-years, --max-stocks, --peak-window, ...). --api-key is still required
for the universe list only.

Requires TradingView Desktop running with CDP on :9222 (check with `tv brief`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import analyze_downtrends  # noqa: E402
from tv_prices import fetch_historical_prices_tv  # noqa: E402


def _patched_fetch(api_key, symbol, from_date, to_date):
    # Original signature takes api_key first; ignored — prices come from the chart.
    return fetch_historical_prices_tv(symbol, from_date, to_date)


# analyze_symbol() calls the module-global fetch_historical_prices, so patching
# the module attribute reroutes every price fetch through TradingView.
analyze_downtrends.fetch_historical_prices = _patched_fetch

if __name__ == "__main__":
    analyze_downtrends.main()
