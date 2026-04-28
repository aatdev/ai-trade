---
name: collect-data
description: Collect OHLCV bars, quote, and indicator values from a live TradingView chart for a given symbol and timeframe, and save the result as a JSON file. Use this skill whenever the user says "collect data", "grab data", "save market data", "скачай данные", "собери данные", "загрузи свечи", mentions downloading/exporting chart data, or wants to snapshot a symbol's price history and indicator readings to a file — even if they don't use the words "collect" or "data" explicitly.
---

# Collect Data Workflow

Collect market data from TradingView for a given symbol and timeframe by running `scripts/collect_data.js`.

## Step 1: Resolve inputs

Ask the user if not provided:
- **Symbol** — e.g. `AAPL`, `BTCUSD`, `ES1!`, `BINANCE:ETHUSDT`
- **Timeframe** — `1`, `5`, `15`, `30`, `60`, `240`, `D`, `W`
- **Bars** (optional) — number of OHLCV candles to save (default: 100, max: 500)

If the user already mentioned a symbol and timeframe in their message, use those — don't ask again.

## Step 2: Run the script

```bash
node scripts/collect_data.js --symbol {SYMBOL} --timeframe {TF} --bars {N}
```

To use the chart as-is without switching symbol/timeframe:
```bash
node scripts/collect_data.js --no-set --bars {N}
```

The script:
1. Switches TradingView to the requested symbol and timeframe (unless `--no-set`)
2. Reads the current chart state
3. Fetches quote, OHLCV bars, and visible indicator values in parallel
4. Saves everything to `./results/{SYMBOL}_{TF}_{timestamp}.json`

## Step 3: Report the result

After the script exits successfully, tell the user:
- Path to the saved file
- Symbol and full name (e.g. "Bitcoin / U.S. dollar")
- Last price
- Number of bars collected
- Number of indicators captured

Example output the script produces:
```
Saved → ./results/BITSTAMP_BTCUSD_1D_2026-04-17_15-02-55.json
  Symbol:     BITSTAMP:BTCUSD (Bitcoin / U.S. dollar)
  Timeframe:  1D
  Last price: 77842
  OHLCV bars: 200
  Indicators: 17
```

## Output file structure

```json
{
  "collected_at": "2026-04-17T15:02:55Z",
  "symbol": "BITSTAMP:BTCUSD",
  "resolution": "1D",
  "quote": { "last": 77842, "open": 76100, "high": 78500, "low": 75900, "volume": 12345 },
  "ohlcv": { "bar_count": 200, "bars": [...] },
  "indicators": [{ "name": "RSI", "values": { "value": 54.3 } }, ...]
}
```

## Common errors

| Error | Fix |
|-------|-----|
| `--symbol required` | Pass `--symbol` or use `--no-set` |
| `CDP connection failed` | TradingView Desktop isn't running, or CDP port 9222 isn't open |
| `Could not extract OHLCV data` | Chart is still loading — wait a moment and retry |
| `Could not retrieve quote` | Same — chart may not have finished loading |