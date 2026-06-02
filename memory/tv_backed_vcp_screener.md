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

**Общий базовый класс (2026-06-01):** ценовой слой `TVClient` вынесен в `scripts/lib/tv_client_base.py` (общий для всех скилов). Per-skill `tv_client.py` теперь тонкие подклассы, конфигурят базу через kwargs: `quote_as_list` (dict vs list), `index_remap` (^GSPC→SP:SPX и т.п.), `cache_disable_env` (VCP_NO_CACHE / CANSLIM_NO_CACHE / FTD_NO_CACHE), `min_bars/bars/settle`. База НЕ импортит ничего скил-специфичного; фундаментал/FMP-делегирование живёт в подклассах. Подключение: подкласс добавляет `scripts/lib` в sys.path и `from tv_client_base import TVClient as _BaseTVClient`.

**Паттерн расширен на другие скилы (2026-05-29):**
- `canslim-screener` — гибрид: подкласс базы тянет цены (N/S/L/M) из TradingView, а фундаментал C/A/I (`get_profile/get_income_statement/get_institutional_holders`) делегирует внутреннему `FMPClient`. Раннер `screen_canslim_tv.py`. ВАЖНО: тут `get_quote` возвращает `list[dict]` (не одиночный dict как в vcp). FMP-ключ ОПЦИОНАЛЕН — без него C/A/N/S/L/M считаются из TV-сканера, только I (институционалы) недоступен.
- `ftd-detector` (2026-06-01) — переведён с FMP на TV: `tv_client.py` = подкласс базы (`quote_as_list=True`, `^GSPC→SP:SPX`, QQQ как есть). API-ключ больше НЕ нужен. SP:SPX отдаёт volume (проверено живьём) — критично, т.к. FTD-гейт требует up-volume в день follow-through. `ftd_detector.py` импортит `TVClient`; тесты Tier C патчат `TVClient` вместо `FMPClient` (`fmp_client.py` оставлен, его Tier A/B тесты живы). Ловушка: гонять в одиночку — collect_russell.js/другой скринер крутит тот же единственный график и рейсит чтения.
- `downtrend-duration-analyzer` — гибрид: `tv_prices.py#fetch_historical_prices_tv` отдаёт цены (DataFrame), раннер `analyze_downtrends_tv.py` монкипатчит `fetch_historical_prices`; вселенная + market cap (`fetch_stock_list`) остаются на FMP. Из-за потолка 400 баров TV-режим видит ~18 мес — для многолетней статистики использовать FMP-режим.
- `us-stock-analysis` — только SKILL.md: техданные через `mcp__tradingview__*` (chart_set_symbol → data_get_ohlcv summary=true → data_get_study_values/quote_get/capture_screenshot), фундаментал/новости остаются на веб-поиске.
- НЕ трогали: market-news-analyst (новости), uptrend-analyzer/sector-analyst (бесплатный breadth-CSV Монти лучше скана TV), finviz-screener (билдер URL). План: `/Users/alex/Etc/ClaudeSpitch/plans/compressed-finding-canyon.md`.
