---
name: metrics_cache_system
description: "Кэш метрик — ДУАЛЬНОЕ хранилище OpenSearch + state/metrics/TICKER/ (metrics.json+ohlcv.json); пишется коллектором, читается OS-first→файл, свежесть ≤2 дней"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6fef6440-2715-4c92-989d-3cbc46de6e79
---

Per-ticker кэш ускоряет скилы: вместо живого графика читают кэш (OpenSearch, fallback на каталог `state/metrics/TICKER/`).

**Хранилище ДУАЛЬНОЕ (с 2026-06-01): OpenSearch + локальные файлы.** Коллектор пишет в оба места; ридеры идут OpenSearch-first, при недоступности/отсутствии дока — локальный файл. Раньше (до этой даты) OpenSearch был удалён и кэш был только на диске — теперь хранение в OS возвращено по просьбе пользователя (хранит ВСЕ данные metrics, не только свечи как старая версия).

**OpenSearch** (`scripts/lib/opensearch.js` JS, секция в `metrics_cache.py` Python): база `OPENSEARCH_URL` (дефолт `http://tw.spitch-dev.ai:9200`), отключить `METRICS_OPENSEARCH=0`. Два индекса:
- `my_tw_metrics` — 1 док/тикер (_id=safeToken, BRK.B→BRK_B), полный снимок metrics. `fundamentals` хранится в _source но НЕ индексируется (`enabled:false`) — иначе взрыв маппинга от history-массивов.
- `my_tw_candles_1d` — 1 док/свечу (легаси-индекс, уже ~1M доков). _id=`TICKER_<секунды>`, поле `time` в **миллисекундах** (легаси-схема!) — писатель умножает на 1000, ридер делит. Новые доки несут `collected_at` (старые ~1M — нет, поэтому их OHLCV считается stale → fallback). Старые индексы `my_tw_tickers`/`my_tw_state` НЕ используются.
- Оба клиента: circuit-breaker (после первой сетевой ошибки перестают долбить сервер на весь процесс), таймаут ~4с.

**Локальная раскладка (каталог на тикер, BRK.B→BRK_B):**
- `metrics.json` — `indicators` (ema20/50/200, sma50/150/200, rsi14, macd, stoch, bb, atr14, returns r_1m/3m/6m/12m — считаются ЛОКАЛЬНО из OHLCV), `fundamentals` (группы как `fundamentals_get` + `history`), `price` (last_close, year_high/low, pct_from_52w_high, avg_volume_50d), `quote`, `collected_at`, `as_of_date`.
- `ohlcv.json` — сырые дневные бары OLDEST-FIRST `{time(sec), date, o,h,l,c,volume}`, до ~1500 баров (≈6 лет).

**Кто пишет:** `scripts/collect_russell.js` (флаг `--no-fundamentals` пропускает фундаментал; OpenSearch-пуш best-effort — при недоступности продолжает только файлами, в строке прогресса `+os` если OS активен). Resume/update берётся из ЛОКАЛЬНОГО metrics.json (`collected_at`/`as_of_date`) — при дуальной записи файл всегда синхронен. В `--update` бары МЁРЖАТСЯ (mergeBars), индикаторы из полной серии — иначе EMA200 null на инкременте.

**Библиотеки:** `scripts/lib/indicators.js` (математика), `scripts/lib/metrics_store.js` (файловый слой: buildMetrics/writeMetrics/writeOhlcv/mergeBars/readOhlcvBars/isFresh, экспортирует safeToken, STALE_DAYS=2, MAX_OHLCV_BARS=1500), `scripts/lib/opensearch.js` (OS-слой: ensureIndices/writeMetrics/writeCandles/readMetrics/readCandlesDoc/listTickers/osActive), `scripts/lib/metrics_cache.py` (Python-ридер OS-first: read_metrics/read_ohlcv/list_tickers + cached_quote/cached_fundamentals/cached_indicators/cached_ohlcv).

**Кто читает (OS-first→файл, далее fallback на live при >2д/miss):**
- markdown-скилы: `node scripts/read_metrics.js TICKER` → exit 0 (свежий) / exit 3 (нет/устарел); `_cache.source` = opensearch|file. Путь к локальным барам в `_cache.ohlcv.path`. Задокументировано в SKILL.md: ticker-analysis, collect-data, us-stock-analysis, technical-analyst, multi-symbol-scan, chart-analysis, daily-buy-scan.
- Скринеры canslim/vcp `tv_client.py`: cache-first в get_quote, get_historical_prices (+canslim _fundamentals) через metrics_cache (теперь OS-first прозрачно). `CANSLIM_NO_CACHE=1`/`VCP_NO_CACHE=1`.
- downtrend `tv_prices.py`: cache-first; кэш СНИМАЕТ 400-баровый лимит live `tv ohlcv`. `DOWNTREND_NO_CACHE=1`.
- `scripts/scan_reversals.py`: `fetch_tickers` через `metrics_cache.list_tickers()` (OS-индекс → fallback на каталог), `fetch_candles` через `read_ohlcv` (OS-first). Вес/`--min-weight` из universe-файла по `--source`.

**Why:** проход по 2000 тикерам с навешиванием индикаторов по каждому — медленно/хрупко; локальный расчёт + единый кэш убирают это. OpenSearch вернули для централизованного доступа к данным несколькими потребителями/машинами; файлы оставлены как надёжный fallback.

**How to apply:** перед анализом тикера сначала кэш (`read_metrics.js`/`metrics_cache.py`, оба OS-first), на устаревшее — live TW. Конфликт ms/sec в `my_tw_candles_1d` — главная ловушка: всегда ms в OS, sec в файле/потребителях. Связано с [[tv_backed_vcp_screener]], [[tv_fundamentals_procedure]].
