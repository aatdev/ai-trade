#!/usr/bin/env node
/**
 * Read a cached metrics snapshot for a ticker (the fast path for skills).
 *
 *   node scripts/read_metrics.js AAPL
 *
 * Prints the state/metrics/TICKER/metrics.json payload with a `_cache` block:
 *   { found, fresh, age_days, stale_days, ohlcv: { available, count, path } }
 *
 * Exit codes let a caller branch without parsing:
 *   0  → snapshot found AND fresh (≤2 days)  → use the cache
 *   3  → snapshot missing or stale           → fall back to a live fetch
 *
 * The full bar series is NOT inlined (it can be ~1000 bars); read the path in
 * `_cache.ohlcv.path` when you need raw OHLCV. On exit 3, pull live from
 * TradingView (data_get_study_values / data_get_ohlcv / fundamentals_get).
 */

import {
  readMetrics,
  metricsAgeDays,
  isFresh,
  STALE_DAYS,
  readOhlcv,
  ohlcvPath,
} from './lib/metrics_store.js';

const ticker = process.argv[2];
if (!ticker) {
  console.error('Usage: node scripts/read_metrics.js <TICKER>');
  process.exit(2);
}

const metrics = readMetrics(ticker);
const fresh = isFresh(metrics);
const ageDays = metricsAgeDays(metrics);
const ohlcv = readOhlcv(ticker);

const payload = {
  ...(metrics ?? { ticker }),
  _cache: {
    found: metrics != null,
    fresh,
    age_days: Number.isFinite(ageDays) ? Number(ageDays.toFixed(2)) : null,
    stale_days: STALE_DAYS,
    ohlcv: {
      available: ohlcv != null,
      count: ohlcv?.count ?? 0,
      as_of_date: ohlcv?.as_of_date ?? null,
      path: ohlcvPath(ticker),
    },
  },
};

console.log(JSON.stringify(payload, null, 2));
process.exit(fresh ? 0 : 3);
