#!/usr/bin/env node
/**
 * Russell 2000 daily candles collector with OpenSearch storage.
 *
 * Reads tickers from russel2000.json, fetches 500 daily bars per ticker,
 * stores in OpenSearch with resume and incremental update support.
 *
 * OpenSearch indices:
 *   my_tw_tickers    — ticker metadata (one doc per ticker)
 *   my_tw_candles_1d — OHLCV candles (one doc per candle, id = TICKER_timestamp)
 *   my_tw_state      — download state (one doc per ticker)
 *
 * Usage:
 *   node scripts/collect_russell.js               # collect all, skip already done
 *   node scripts/collect_russell.js --update      # refresh fresh bars (10-bar overlap)
 *   node scripts/collect_russell.js --from CRDO   # resume from specific ticker
 *   node scripts/collect_russell.js --limit 50    # process only first N tickers
 *   node scripts/collect_russell.js --ticker AAPL # single ticker
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { setSymbol, setTimeframe } from '../src/core/chart.js';
import { getOhlcv, getQuote } from '../src/core/data.js';
import { disconnect } from '../src/connection.js';

// ─── Config ──────────────────────────────────────────────────────────────────

const OS_BASE = process.env.OPENSEARCH_URL ?? 'http://tw.spitch-dev.ai:9200';
const BARS_FULL = 1000;
const UPDATE_OVERLAP = 5; // safety overlap added to missing-days count
const UPDATE_MIN = 10; // never fetch fewer than this in update mode
const SLEEP_CHART = 2500; // ms to wait after symbol switch
const SLEEP_BETWEEN = 800;

const IDX_TICKERS = 'my_tw_tickers';
const IDX_CANDLES = 'my_tw_candles_1d';
const IDX_STATE = 'my_tw_state';

// ─── Args ─────────────────────────────────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { update: false, from: null, limit: null, ticker: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--update') opts.update = true;
    else if (args[i] === '--from') opts.from = args[++i];
    else if (args[i] === '--limit') opts.limit = parseInt(args[++i]);
    else if (args[i] === '--ticker') opts.ticker = args[++i];
  }
  return opts;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// TradingView returns bar.time in UNIX seconds
function barDate(tsSec) {
  return new Date(tsSec * 1000).toISOString().slice(0, 10);
}

function candleId(ticker, tsSec) {
  return `${ticker}_${tsSec}`;
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(fromDateStr, toDateStr) {
  const from = new Date(fromDateStr + 'T00:00:00Z');
  const to = new Date(toDateStr + 'T00:00:00Z');
  return Math.round((to - from) / 86400000);
}

// ─── OpenSearch client ────────────────────────────────────────────────────────

async function osRequest(method, path, body) {
  const url = `${OS_BASE}${path}`;
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = typeof body === 'string' ? body : JSON.stringify(body);

  const res = await fetch(url, opts);
  const text = await res.text();

  if (!res.ok && res.status !== 404 && res.status !== 409) {
    throw new Error(`OpenSearch ${method} ${path} → ${res.status}: ${text.slice(0, 300)}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function osGet(path) {
  return osRequest('GET', path);
}
async function osPut(path, body) {
  return osRequest('PUT', path, body);
}
async function osPost(path, body) {
  return osRequest('POST', path, body);
}

// ─── Index management ─────────────────────────────────────────────────────────

async function ensureIndices() {
  const tickerMapping = {
    mappings: {
      properties: {
        ticker: { type: 'keyword' },
        name: { type: 'text', fields: { keyword: { type: 'keyword' } } },
        sector: { type: 'keyword' },
        exchange: { type: 'keyword' },
        asset_class: { type: 'keyword' },
        location: { type: 'keyword' },
        currency: { type: 'keyword' },
        weight_pct: { type: 'float' },
        market_value: { type: 'double' },
        price: { type: 'float' },
      },
    },
  };

  const candleMapping = {
    mappings: {
      properties: {
        ticker: { type: 'keyword' },
        time: { type: 'long' },
        date: { type: 'date', format: 'yyyy-MM-dd' },
        open: { type: 'float' },
        high: { type: 'float' },
        low: { type: 'float' },
        close: { type: 'float' },
        volume: { type: 'long' },
      },
    },
  };

  const stateMapping = {
    mappings: {
      properties: {
        ticker: { type: 'keyword' },
        status: { type: 'keyword' }, // pending | done | failed | updating
        bars_count: { type: 'integer' },
        last_bar_time: { type: 'long' },
        last_bar_date: { type: 'date', format: 'yyyy-MM-dd' },
        last_collected_at: { type: 'date' },
        error: { type: 'text' },
      },
    },
  };

  for (const [idx, mapping] of [
    [IDX_TICKERS, tickerMapping],
    [IDX_CANDLES, candleMapping],
    [IDX_STATE, stateMapping],
  ]) {
    const exists = await osGet(`/${idx}`);
    if (exists?.status === 404 || exists?.error?.type === 'index_not_found_exception') {
      await osPut(`/${idx}`, mapping);
      console.log(`  Created index: ${idx}`);
    }
  }
}

// ─── State helpers ────────────────────────────────────────────────────────────

async function getState(ticker) {
  const r = await osGet(`/${IDX_STATE}/_doc/${ticker}`);
  return r?.found ? r._source : null;
}

async function saveState(ticker, fields) {
  await osPost(`/${IDX_STATE}/_doc/${ticker}`, { ticker, ...fields });
}

// ─── Ticker metadata ──────────────────────────────────────────────────────────

async function saveTicker(meta) {
  const doc = {
    ticker: meta.Ticker,
    name: meta.Name,
    sector: meta.Sector,
    exchange: meta.Exchange,
    asset_class: meta['Asset Class'],
    location: meta.Location,
    currency: meta.Currency,
    weight_pct: parseFloat(meta['Weight (%)']) || 0,
    market_value: parseFloat((meta['Market Value'] || '').replace(/,/g, '')) || 0,
    price: parseFloat((meta.Price || '').replace(/,/g, '')) || 0,
  };
  await osPost(`/${IDX_TICKERS}/_doc/${meta.Ticker}`, doc);
}

// ─── Candles storage ──────────────────────────────────────────────────────────

async function bulkUpsertCandles(ticker, bars) {
  if (!bars.length) return 0;

  const lines = [];
  for (const bar of bars) {
    const id = candleId(ticker, bar.time);
    lines.push(JSON.stringify({ index: { _index: IDX_CANDLES, _id: id } }));
    lines.push(
      JSON.stringify({
        ticker,
        time: bar.time * 1000, // stored as ms, bar.time is seconds from TradingView
        date: barDate(bar.time),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume ?? 0,
      })
    );
  }

  const body = lines.join('\n') + '\n';
  const r = await osRequest('POST', '/_bulk', body);
  const errors = r?.items?.filter((i) => i.index?.error)?.length ?? 0;
  if (errors) console.warn(`    Bulk errors: ${errors}`);
  return bars.length - errors;
}

async function getLastCandleTime(ticker) {
  const r = await osPost(`/${IDX_CANDLES}/_search`, {
    size: 1,
    query: { term: { ticker } },
    sort: [{ time: 'desc' }],
    _source: ['time'],
  });
  const hit = r?.hits?.hits?.[0];
  return hit ? hit._source.time : null;
}

// ─── TradingView data ─────────────────────────────────────────────────────────

async function fetchBars(symbol, count) {
  await setSymbol({ symbol });
  await sleep(SLEEP_CHART);
  await setTimeframe({ timeframe: 'D' });
  await sleep(1000);

  const [quote, ohlcv] = await Promise.all([getQuote({}), getOhlcv({ count })]);

  return { quote, bars: ohlcv.bars ?? [] };
}

// ─── Main loop ────────────────────────────────────────────────────────────────

async function processTicker(ticker, meta, opts) {
  const state = await getState(ticker);
  const today = todayDate();

  // Decide how many bars to fetch
  let barsToFetch = BARS_FULL;
  let isUpdate = false;

  if (state?.status === 'done') {
    if (!opts.update) {
      process.stdout.write('skip\n');
      return 'skipped';
    }

    // Already refreshed today — nothing to do
    const collectedDate = state.last_collected_at?.slice(0, 10);
    if (collectedDate === today) {
      process.stdout.write('skip (today)\n');
      return 'skipped';
    }

    // Fetch only missing days (+ overlap); fall back to full if gap is too large
    const missing = state.last_bar_date ? daysBetween(state.last_bar_date, today) : null;
    if (missing != null && missing > 0 && missing + UPDATE_OVERLAP < BARS_FULL) {
      barsToFetch = Math.max(missing + UPDATE_OVERLAP, UPDATE_MIN);
    }
    isUpdate = true;
  }

  // Fetch from TradingView
  await saveState(ticker, {
    status: isUpdate ? 'updating' : 'pending',
    last_collected_at: new Date().toISOString(),
  });

  await saveTicker(meta);

  const { quote, bars } = await fetchBars(ticker, barsToFetch);

  if (!bars.length) throw new Error('No bars returned');

  // On update: deduplicate against stored data by only inserting new candles.
  // bulkUpsertCandles uses "index" action which overwrites by _id, so overlap
  // bars are safely re-written with latest values.
  const saved = await bulkUpsertCandles(ticker, bars);

  const lastBar = bars[bars.length - 1];
  await saveState(ticker, {
    status: 'done',
    bars_count: saved,
    last_bar_time: lastBar.time * 1000,
    last_bar_date: barDate(lastBar.time),
    last_collected_at: new Date().toISOString(),
    error: null,
  });

  const tag = isUpdate ? 'upd' : 'new';
  process.stdout.write(
    `✓  [${tag}] bars=${saved}/${barsToFetch}  last=${barDate(lastBar.time)}  price=${quote.last ?? quote.close}\n`
  );
  return 'done';
}

async function main() {
  const opts = parseArgs();

  // Load tickers
  const russelPath = resolve('state/russel2000.json');
  const allTickers = JSON.parse(readFileSync(russelPath, 'utf-8'));
  console.log(`Loaded ${allTickers.length} tickers from russel2000.json`);

  // Apply --ticker filter
  let tickers = opts.ticker ? allTickers.filter((t) => t.Ticker === opts.ticker) : allTickers;

  // Apply --from filter (resume)
  if (opts.from) {
    const idx = tickers.findIndex((t) => t.Ticker === opts.from);
    if (idx === -1) {
      console.error(`Ticker ${opts.from} not found`);
      process.exit(1);
    }
    tickers = tickers.slice(idx);
    console.log(`Resuming from ${opts.from} (${tickers.length} tickers remaining)`);
  }

  // Apply --limit
  if (opts.limit) tickers = tickers.slice(0, opts.limit);

  const mode = opts.update ? 'UPDATE' : 'COLLECT';
  console.log(
    `\nMode: ${mode} | Tickers: ${tickers.length} | Bars: ${opts.update ? 'auto (missing days + ' + UPDATE_OVERLAP + ' overlap)' : BARS_FULL}\n`
  );

  // Ensure indices exist
  await ensureIndices();

  const stats = { done: 0, updated: 0, skipped: 0, failed: 0 };

  for (let i = 0; i < tickers.length; i++) {
    const meta = tickers[i];
    const sym = meta.Ticker;
    process.stdout.write(`[${String(i + 1).padStart(4)}/${tickers.length}] ${sym.padEnd(8)} `);

    try {
      const result = await processTicker(sym, meta, opts);
      if (result === 'skipped') stats.skipped++;
      else if (opts.update) stats.updated++;
      else stats.done++;
    } catch (err) {
      process.stdout.write(`✗  ${err.message}\n`);
      await saveState(sym, {
        status: 'failed',
        error: err.message,
        last_collected_at: new Date().toISOString(),
      }).catch(() => {});
      stats.failed++;
    }

    if (i < tickers.length - 1) await sleep(SLEEP_BETWEEN);
  }

  console.log(`\n${'━'.repeat(50)}`);
  console.log(
    `Collected: ${stats.done}  Updated: ${stats.updated}  Skipped: ${stats.skipped}  Failed: ${stats.failed}`
  );

  await disconnect();
}

main().catch((err) => {
  console.error('\nFatal:', err.message);
  process.exit(1);
});
