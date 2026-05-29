#!/usr/bin/env python3
"""
Run the CANSLIM screener with price data sourced from live TradingView.

Monkeypatches screen_canslim.FMPClient with the hybrid TVClient: the price-based
components (N newness, S supply/demand, L leadership, M market direction) are
computed from daily bars served by a running TradingView Desktop (via the `tv`
CLI / CDP on :9222), while the fundamental components (C earnings, A annual
growth, I institutional) are delegated to an internal FMPClient.

Why: the FMP free tier gates most symbols' price history at the API level, so a
real universe scan burns the daily quota fast. Routing price through TradingView
removes that limit; the FMP key is then only spent on C/A/I fundamentals.

All CLI flags of screen_canslim.py are accepted verbatim (--api-key,
--universe, --max-candidates, --top, --output-dir, ...). --api-key is still
required — but only for the fundamental components.

Requires TradingView Desktop running with CDP on :9222 (check with `tv brief`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import screen_canslim  # noqa: E402
from tv_client import TVClient  # noqa: E402

# Swap the data layer. screen_canslim binds FMPClient at import time, so
# patching the module attribute is enough — main() reads screen_canslim.FMPClient.
screen_canslim.FMPClient = TVClient

if __name__ == "__main__":
    screen_canslim.main()
