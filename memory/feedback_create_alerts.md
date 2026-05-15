---
name: Создание алертов в TradingView Desktop
description: Рабочий обходной путь для создания price-алертов через MCP, когда штатный mcp__tradingview__alert_create возвращает price_set:false / dom_fallback
type: feedback
originSessionId: 0c525538-c087-49ad-8d4f-07848255f5c0
---
Штатный `mcp__tradingview__alert_create` в этом репозитории НЕ РАБОТАЕТ для текущего DOM TradingView Desktop — возвращает `success: false, price_set: false, source: "dom_fallback"`. Причина: селекторы в `src/core/alerts.js:24-45` ищут `[class*="alert"] input[...]`, а актуальный DOM использует хэшированные классы вида `input-RUSovanF`, и в дереве нет узла с подстрокой `alert` в classList.

**Why:** проверено в живой сессии 2026-05-02 на ONON — 5 подряд вызовов alert_create вернули dom_fallback failure, в `list_alerts` алертов не появилось. Прямой POST на `https://pricealerts.tradingview.com/create_alert` блокируется (CORS / отсутствует CSRF-токен) — fetch падает с `TypeError: Failed to fetch`. GET-эндпоинт `list_alerts` при этом работает.

**How to apply:** когда пользователь просит создать алерт(ы), используй этот рабочий пайплайн через `mcp__tradingview__ui_click` + `mcp__tradingview__ui_evaluate`:

1. Убедиться что нужный символ загружен: `chart_set_symbol` + `chart_get_state` (дождаться, что чарт реально обновился — после set_symbol сразу `chart_ready: false`).
2. На каждый алерт повторять цикл:

   а) Открыть диалог:
   ```
   ui_click(by="aria-label", value="Create alert")
   ```
   sleep ~1.5s — диалогу нужно время на рендер.

   б) Заполнить цену и сабмитнуть в одном ui_evaluate. **Важно: использовать `document.execCommand('insertText')`, а НЕ `Object.getOwnPropertyDescriptor(...).set` — последний не пробивает React-state и при втором+ открытии диалога подряд цена улетит как дефолтная (текущая рыночная), а не как заданная. Проверено 2026-05-04 на CRWV: первая попытка через ns.call дала $113 → реально создано $122.10. Через execCommand($113) сразу легло как $113.00.**
   ```js
   (function() {
     const inp = Array.from(document.querySelectorAll('input')).filter(i => i.offsetParent !== null)[0];
     if (!inp) return { error: 'no input' };
     inp.focus();
     inp.select();
     document.execCommand('delete', false);
     document.execCommand('insertText', false, '37.90');   // подставить цену
     inp.dispatchEvent(new Event('change', { bubbles: true }));
     inp.blur();
     const b = Array.from(document.querySelectorAll('button'))
       .filter(x => /^create$/i.test(x.textContent.trim()) && x.offsetParent !== null)[0];
     if (b) b.click();
     return { value: inp.value, clicked: !!b };
   })()
   ```
   sleep ~1.2s после клика.

3. Проверить факт создания через синхронный XHR на REST API (это работает на чтение):
   ```js
   (function() {
     const xhr = new XMLHttpRequest();
     xhr.open('GET', 'https://pricealerts.tradingview.com/list_alerts', false);
     xhr.withCredentials = true;
     xhr.send();
     const data = JSON.parse(xhr.responseText);
     return (data.r || [])
       .filter(a => /SYMBOL/i.test(a.symbol))
       .map(a => ({ id: a.alert_id, message: a.message, price: a.condition?.series?.[1]?.value, active: a.active }));
   })()
   ```

**Ограничения этого обходного пути:**
- Message textarea не видна в дефолтном диалоге → сообщения уходят дефолтные `"SYMBOL Crossing PRICE"`. Кастомные тексты придётся проставлять вручную через Edit alert.
- Условие всегда получается `crossing` (двунаправленное) — направленные `crossing_up` / `crossing_down` через дефолтный диалог не выставить без раскрытия секции Settings.
- Если пользователю нужны кастомные сообщения или направление — предупредить заранее, не делать вид что всё ок.

**Удаление мусорных алертов через UI** (REST endpoint `/remove_alert`, `/delete_alert` etc. отдают `no_such_endpoint`; `mcp__tradingview__alert_delete delete_all=true` снесёт ВСЕ алерты пользователя — опасно, у юзера обычно много чужих тикеров):
1. `mcp__tradingview__ui_open_panel(panel="alerts", action="open")`.
2. Переключиться на вкладку Alerts (не Log): кликнуть по `button.segmentedControlBase-...` с текстом `Alerts`.
3. На каждый удаляемый — найти `[data-name="alert-item-description"]` с нужным текстом, подняться до родителя содержащего `[data-name="alert-delete-button"]`, кликнуть delete.
4. Появится confirm dialog → кликнуть `button.actionButton-...` с текстом `Delete`.
5. sleep ~0.8s между алертами.

**TODO для починки штатного инструмента** (если когда-нибудь править `src/core/alerts.js`): заменить селектор на `Array.from(document.querySelectorAll('input')).filter(i => i.offsetParent !== null)[0]` — без привязки к классам. Так же сделать с textarea и кнопкой Create.
