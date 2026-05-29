---
name: tv_fundamentals_procedure
description: "Как доставать фундаментальные данные (выручка, маржи, баланс, мультипликаторы, годовые/квартальные ряды) из TradingView"
metadata: 
  node_type: memory
  type: project
  originSessionId: dbd391d2-f0eb-4613-b215-6fd151f9f218
---

Fundamentals из TradingView берутся через scanner-эндпоинт, выполненный **изнутри страницы tradingview.com** (по CDP), чтобы унаследовать авторизационные cookie:

`https://scanner.tradingview.com/symbol?symbol=<EXCHANGE>:<TICKER>&fields=<csv>&no_404=true`

**Why:** прямой fetch снаружи отдаёт 401/урезанный набор; запрос из контекста залогиненной страницы возвращает полный набор полей (включая платные). Текст правой панели Symbol Details даёт только подписи осей графиков — не сами числа.

**How to apply:**
- Штатный инструмент (по архитектуре репо): MCP `mcp__tradingview__fundamentals_get` ({symbol?, history?}) и CLI `tv fundamentals NYSE:VSCO [--history]`. Логика — `src/core/fundamentals.js` (get), регистрация в `src/tools/fundamentals.js`, `src/cli/commands/fundamentals.js`, re-export из `src/core/index.js`. ВАЖНО: новый MCP-инструмент появляется только после рестарта MCP-сервера.
- Standalone-скрипт (без npm link / без рестарта сервера): `node scripts/tv_fundamentals.mjs NYSE:VSCO [--history] [--json]`. Без символа берёт его с активного графика или парсит из URL страницы `/symbols/NYSE-VSCO/`.
- Через MCP: `ui_evaluate` НЕ ждёт промисов (возвращает `{}`). Паттерн: первым вызовом запустить `fetch(...).then(...→ window.__fnd=...)`, вторым вызовом прочитать `JSON.stringify(window.__fnd)`. В Node-скрипте проще — `evaluateAsync` (awaitPromise:true) ждёт fetch напрямую.
- Поля: суффиксы `_ttm` (TTM), `_fq` (последний квартал), `_fy` (год). История — массивы с суффиксом `_h` (`total_revenue_fy_h`, `net_income_fq_h`, `earnings_per_share_diluted_fq_h`), порядок: свежий период первым.
- В десктопе несколько таргетов tradingview.com (график `/chart/`, страница символа `/symbols/...`); fetch работает с любого, но символ удобнее тянуть с `/chart/`. Символ берётся через `window.TradingViewApi.activeChart().symbol()` (НЕ `_activeChartWidgetWV.value().activeChart()` — такого метода нет).

**Где уже используется (скиллы переведены на тул):**
- `ticker-analysis` (Шаг 2 fundamental.md) и `us-stock-analysis` — цифры из `fundamentals_get`, web только для нарратива (гайденс, сегменты, beat/miss, рейтинги).
- `canslim-screener` (TradingView-режим): компоненты C (квартальные earnings) и A (годовой рост) теперь из `tv fundamentals` (через `tv_client.py` → FMP-совместимая форма income statement из history-рядов). **FMP-ключ больше не обязателен** — остаётся только I (институционалы) на FMP/Finviz; EMA считается локально. Проверено на AAPL: C score 60 (EPS +22%), A считается из годового diluted EPS.
- `vcp-screener`: скоринг ценовой, фундаментал не трогает; заметка — обогащать ШОРТ-ЛИСТ (не весь скан) через `fundamentals_get`.
- `tradingview-mcp/SKILL.md` — добавлен раздел про тул + оценка размера вывода.

Связано с [[tv_backed_vcp_screener]] — тот же приём «гонять запросы из живой страницы вместо платного FMP».
