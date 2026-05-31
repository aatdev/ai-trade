---
name: metrics_cache_system
description: "Кэш state/metrics/TICKER/ (metrics.json + ohlcv.json) — быстрый путь для скилов (индикаторы/фундаментал/цена/сырые бары), пишется коллектором, свежесть ≤2 дней"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6fef6440-2715-4c92-989d-3cbc46de6e79
---

Per-ticker кэш ускоряет скилы: вместо живого графика читают каталог `state/metrics/TICKER/`.

**Раскладка (каталог на тикер, BRK.B→BRK_B):**
- `metrics.json` — `indicators` (ema20/50/200, sma50/150/200, rsi14, macd, stoch, bb, atr14, returns r_1m/3m/6m/12m — считаются ЛОКАЛЬНО из OHLCV, не с графика), `fundamentals` (те же группы, что `fundamentals_get`, + `history`), `price` (last_close, year_high/low, pct_from_52w_high, avg_volume_50d), `quote`, `collected_at`, `as_of_date`.
- `ohlcv.json` — сырые дневные бары OLDEST-FIRST `{time(sec), date, o,h,l,c,volume}`, до ~1500 баров (≈6 лет). Скриншотов в кэше нет.

**Кто пишет:** `scripts/collect_russell.js` (флаг `--no-fundamentals` пропускает фундаментал). **OpenSearch удалён полностью** — кэш на диске единственный store; resume/update берётся из metrics.json (`collected_at`/`as_of_date`). В `--update` бары МЁРЖАТСЯ с существующими (mergeBars), индикаторы считаются из полной слитой серии — иначе EMA200 был бы null на инкременте. Свежесть: `node scripts/collect_russell.js --update` (S&P 500: `--source snp500`).

**Библиотеки:** `scripts/lib/indicators.js` (математика), `scripts/lib/metrics_store.js` (buildMetrics/writeMetrics/writeOhlcv/mergeBars/readOhlcvBars/isFresh, STALE_DAYS=2, MAX_OHLCV_BARS=1500), `scripts/lib/metrics_cache.py` (Python-ридер: cached_quote/cached_fundamentals/cached_indicators/cached_ohlcv + read_ohlcv).

**Кто читает (все с fallback на live при >2д/miss):**
- markdown-скилы: `node scripts/read_metrics.js TICKER` → exit 0 (свежий) / exit 3 (нет/устарел). Путь к барам в `_cache.ohlcv.path`. Задокументировано в SKILL.md: ticker-analysis, collect-data, us-stock-analysis, technical-analyst, multi-symbol-scan, chart-analysis, daily-buy-scan (освежает кэш в шаге 0).
- Скринеры canslim/vcp `tv_client.py`: cache-first в get_quote, get_historical_prices (+canslim _fundamentals) — при свежем кэше прогон по всей вселенной БЕЗ живого TradingView (раньше сырые бары были пробелом — теперь закрыт ohlcv.json). Индексы ^GSPC/^VIX не собираются → всегда live. Отключить: `CANSLIM_NO_CACHE=1`/`VCP_NO_CACHE=1`.
- downtrend `tv_prices.py`: cache-first; кэш (до ~1500 баров) СНИМАЕТ 400-баровый лимит live `tv ohlcv`, даёт многолетние окна. `DOWNTREND_NO_CACHE=1`.
- `scripts/scan_reversals.py`: целиком переведён с OpenSearch на кэш — fetch_candles из ohlcv.json, fetch_tickers перечисляет state/metrics/* (вес для сортировки/--min-weight из universe-файла по `--source`).

**Why:** проход по 2000 тикерам с навешиванием индикаторов/переключением чарта по каждому — медленно и хрупко; локальный расчёт из скачанных баров + единый кэш с сырыми барами убирают это.

**How to apply:** перед анализом тикера сначала кэш (`read_metrics.js`/`metrics_cache.py`), на устаревшее — live TW. Связано с [[tv_backed_vcp_screener]], [[tv_fundamentals_procedure]].
