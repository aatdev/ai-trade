---
name: tv-ws-chartapi-protocol
description: Внутренний WS chart-api TradingView (ChartApiInstance) — снятый протокол для detached-сбора свечей без переключения графика; задел для параллельного коллектора
metadata: 
  node_type: memory
  type: reference
  originSessionId: d4163123-ccce-4707-8cb5-c19b87e160e2
---

Внутренний websocket chart-api TradingView доступен из страницы как `window.ChartApiInstance` (он же `window.TradingViewApi._chartApiInstance`). Через него можно тянуть дневные свечи **произвольного** тикера, не трогая видимый график, и держать несколько серий на одном сокете → честный параллелизм внутри одной страницы (потолок 10×+ к нынешнему последовательному коллектору). Это задел для варианта «#2» ускорения сбора (см. [[metrics_cache_system]], коллектор `scripts/collect_russell.js`).

**Снятый протокол** (перехвачены реальные аргументы патчем методов + смена символа на MSFT, `tmp/probe_capture.mjs`):
```
createSession(csId, handlerObj)              // csId вида "cs_eSwYWdZiagXA"; handlerObj — объект-приёмник уведомлений
chartCreateSession(csId, true)
resolveSymbol(csId, symId, spec, cb)         // symId "sds_sym_314"; spec = "NASDAQ:MSFT" ИЛИ '={"adjustment":"splits","symbol":"MSFT"}'
createSeries(csId, seriesId, "s1", symId, "1D", 300, {value:"12M",type:"period-back"}, cb)
                                             // seriesId "sds_159", scopeId "s1", barCount 300, range {value,type:"period-back"}
modifySeries(csId, seriesId, "s1", symId, "1D", null, {value,type}, cb)   // для смены символа существующей серии
requestMoreData(csId, seriesId, count, cb)   // догрузка истории
```
Данные приходят в `handlerObj`, зарегистрированный в `createSession`; ChartApiInstance маршрутизирует уведомления через `_dispatchNotification`/`_invokeNotificationHandler` по sessionId. Сообщения с барами — `timescale_update`/`du`.

**Что осталось доделать для рабочего detached-сбора** (НЕ сделано на 2026-06-02): реализовать объект-обработчик сессии (методы перечислить из живой сессии в `cai._sessions`) и распарсить payload `timescale_update`. Сигнатуры минифицированы (`createSeries(e,t,s,n,i,o,r,a)`), поэтому опираться на снятые векторы выше, а не угадывать. Риск: API недокументирован, хрупок к обновлениям TradingView — делать отдельным PR с проверкой на нескольких тикерах.

**Уже сделано на 2026-06-02 (вариант #1, в git):** убран латентный баг — `setSymbol` в `src/core/chart.js` упирался в 10-секундный таймаут DOM-эвристики `waitForChartReady` (селектор `[class*="bar"]` + символ из шапки не стабилизировались), съедая ~10с/тикер. Добавлена опция `setSymbol({wait:false})`; коллектор ждёт по модели данных напрямую (`mainSeries().symbolInfo().name === ticker` + стабильный `bars().size()`, ~150мс). Результат ~10×: S&P500 ~87мин→~8мин, Russell2000 ~5.8ч→~33мин. Сигнал готовности: `cw.symbol()`="NASDAQ:MSFT", `symbolInfo().name`="MSFT", `cw.resolution()`="1D".
