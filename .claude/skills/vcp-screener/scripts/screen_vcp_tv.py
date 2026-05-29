#!/usr/bin/env python3
"""
Run the VCP screener against live TradingView data instead of FMP.

Monkeypatches screen_vcp.FMPClient with TVClient (which sources daily OHLCV from
a running TradingView Desktop via the `tv` CLI / CDP) and delegates to the
screener's normal main(). All CLI flags of screen_vcp.py are accepted verbatim
(--universe, --strict, --max-candidates, tuning params, --output-dir, ...).

Requires TradingView Desktop running with CDP on :9222.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import screen_vcp  # noqa: E402
from tv_client import TVClient  # noqa: E402

# Swap the data layer. screen_vcp binds FMPClient at import time, so patching
# the module attribute is enough — main() reads screen_vcp.FMPClient.
screen_vcp.FMPClient = TVClient

if __name__ == "__main__":
    screen_vcp.main()
