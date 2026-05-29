---
name: tv-backed-vcp-screener
description: Как гонять VCP-скринер на данных TradingView в обход платного/гейтящего FMP API
metadata: 
  node_type: memory
  type: project
  originSessionId: bdacf298-6d4c-48c3-80c9-971a4fd7eaf1
---

FMP free tier непригоден для VCP-скрина: эндпоинт `sp500-constituent` платный (402), плюс symbol-гейтинг (большинство тикеров отдают "Invalid/Restricted"). Решение — гонять скринер на данных живого TradingView.

**Инструменты (созданы 2026-05-29):**
- `.claude/skills/vcp-screener/scripts/tv_client.py` — `TVClient` с интерфейсом `FMPClient`, тянет 400 дневных баров через `tv` CLI (`node src/cli/index.js symbol/timeframe/ohlcv`) по CDP. Quote синтезируется из баров. Символы с <200 баров пропускаются.
- `.claude/skills/vcp-screener/scripts/screen_vcp_tv.py` — раннер: `screen_vcp.FMPClient = TVClient` + штатный `main()`. Принимает все флаги `screen_vcp.py`.
- `.claude/skills/vcp-screener/scripts/aggregate_shortlist.py` — свод JSON-отчётов в шорт-лист.

**Нюансы:** нужен запущенный TradingView Desktop (CDP :9222); ~9с/тикер; чанки ≤150 гонять ПОСЛЕДОВАТЕЛЬНО (один график TradingView, параллельно нельзя); JSON сохраняет топ-20; в скане по малому числу имён `rs_percentile` считается ВНУТРИ вселенной, не S&P 500. Алерты ставить через [[feedback-create-alerts]] / скилл `signals-alerts`. Снапшот сессии: `results/vcp/SESSION_2026-05-29.md`.

**Ограничение CLI (важно):** `tv ohlcv` отдаёт максимум 500 баров, а его пайповый stdout режется на 64 КБ (≈430 баров JSON, ломается на полуслове). Поэтому безопасный потолок — **400 баров ≈ 18 мес** дневной истории на тикер. Именно поэтому vcp использует `BARS=400`. Если просить больше — JSON приходит обрезанным и `json.loads` падает → "no bars".

**Паттерн расширен на другие скилы (2026-05-29):**
- `canslim-screener` — гибрид: `tv_client.py` тянет цены (компоненты N/S/L/M) из TradingView, а фундаментал C/A/I (`get_profile/get_income_statement/get_institutional_holders/calculate_ema`) делегирует внутреннему `FMPClient`. Раннер `screen_canslim_tv.py`. ВАЖНО: тут `get_quote` возвращает `list[dict]` (не одиночный dict как в vcp). FMP-ключ всё ещё нужен — только для фундаментала.
- `downtrend-duration-analyzer` — гибрид: `tv_prices.py#fetch_historical_prices_tv` отдаёт цены (DataFrame), раннер `analyze_downtrends_tv.py` монкипатчит `fetch_historical_prices`; вселенная + market cap (`fetch_stock_list`) остаются на FMP. Из-за потолка 400 баров TV-режим видит ~18 мес — для многолетней статистики использовать FMP-режим.
- `us-stock-analysis` — только SKILL.md: техданные через `mcp__tradingview__*` (chart_set_symbol → data_get_ohlcv summary=true → data_get_study_values/quote_get/capture_screenshot), фундаментал/новости остаются на веб-поиске.
- НЕ трогали: market-news-analyst (новости), uptrend-analyzer/sector-analyst (бесплатный breadth-CSV Монти лучше скана TV), finviz-screener (билдер URL). План: `/Users/alex/Etc/ClaudeSpitch/plans/compressed-finding-canyon.md`.
