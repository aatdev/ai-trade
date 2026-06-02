---
name: cts_tv_data_layer
description: claude-trading-skills больше не нуждается в FMP — 9 скринеров переведены на TV-backed tv_client (живой график + scanner)
metadata: 
  node_type: memory
  type: project
  originSessionId: bac12a38-c7f5-4d94-a5d8-850fadbb2da0
---

В репозитории `/Users/alex/Projects/Repos/claude-trading-skills` FMP заменён на
данные из TradingView для 9 скилов (`vcp-screener`, `canslim-screener`,
`ftd-detector`, `market-top-detector`, `macro-regime-detector`, `pead-screener`,
`parabolic-short-trade-planner`, `earnings-trade-analyzer`,
`ibd-distribution-day-monitor`). **ОДНА копия** общих модулей лежит в
`scripts/lib/`: `tv_client_base.py` (общий `TVClient`), `metrics_cache.py`
(OpenSearch-first ридер, см. [[metrics_cache_system]]), `tv_client.py`
(экспортит `FMPClient = TVClient` (dict-история), `TVClientListHistory`
(list-история, только для earnings) и `ApiCallBudgetExceeded`). **Без симлинков
и без копий**: каждый entry-скрипт добавляет `scripts/lib` в `sys.path` одной
самодостаточной строкой перед импортом (`_sys.path.insert(0, …/../../scripts/lib)`)
и импортит `from tv_client import FMPClient` (earnings:
`TVClientListHistory as FMPClient`). Старый `fmp_client.py` оставлен ради
юнит-тестов. Кэш отключается одним `TV_NO_CACHE=1`. **Подводный камень упаковки:**
`package_skills.py` пакует только файлы внутри `skills/<skill>/`, поэтому общие
модули из `scripts/lib/` НЕ попадают в `.skill`-архивы — для standalone-поставки
их надо добавить в упаковщик. Из репозитория всё работает.

**Why:** FMP free-tier гейтит большинство тикеров; TradingView отдаёт бары и
scanner-фундаментал без лимитов и без ключа.

**How to apply:**
- Нужен запущенный TradingView Desktop (CDP :9222) и глобальный `tv` (`npm link`
  в tradingview-mcp-jackson). `TV_MCP_REPO` (дефолт — путь к этому репо) указывает
  на `state/sp500.csv` и `scripts/tv_earnings_calendar.mjs`.
- `ibd` и `parabolic` имеют собственный гейт api-ключа → передавать `--api-key tv`
  (значение игнорируется). `ibd` требует pyyaml → запускать через `.venv/bin/python`.
- 4 недостающих метода реализованы поверх TV: `get_company_profile(s)` и
  `get_income_statement` — из `tv fundamentals` (scanner); `get_vix_term_structure`
  — TVC:VIX / **CBOE:VIX3M** (TVC:VIX3M баров не отдаёт); `get_treasury_rates` —
  TVC:US02Y/US10Y; `get_earnings_calendar` — новый `scripts/tv_earnings_calendar.mjs`
  в tradingview-mcp-jackson (POST на scanner.tradingview.com/america/scan изнутри
  залогиненной страницы, без Content-Type чтобы обойти CORS preflight).
- Ловушки форм: прямой `get_quote` отдаёт `[dict]`, а `get_batch_quotes`
  разворачивает в `{sym: dict}`; `earnings-trade-analyzer` ждёт от
  `get_historical_prices` голый `list[dict]` (остальные — `{symbol, historical}`).
- Известное ограничение: профиль-фаза earnings/pead тянет профиль на каждый
  тикер календаря — промахи кэша гонят график по одному (медленно на широком
  small-cap универсе). Доработка: батч-профили через scanner одним запросом.
  Документация: `docs/TV_DATA_LAYER.md`.
