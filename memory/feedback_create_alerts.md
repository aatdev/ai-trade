---
name: tradingview-desktop
description: "Штатный alert_create поддерживает Multi-condition (price + volume в одном алерте через \"Add condition\"), с настраиваемыми условиями. React-controlled inputs требуют CDP-mouse-click + Input.insertText + dispatch input event + Tab — обычный execCommand не персистит state."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3f5f8089-7f51-48dd-91ac-f72177ec9fc6
---

С 2026-05-15 `src/core/alerts.js#create` поддерживает Multi-condition flow напрямую через UI диалога TradingView. Параметры:

- `price`, `volume` — значения для соответствующих условий
- `price_condition`, `volume_condition` — типы условий ("Greater Than", "Less Than", "Crossing Up", "Crossing Down", "Crossing", etc.)

**Поведение:**
- только `price` → стандартный однострочный алерт на Price
- только `volume` → main source переключается на "Vol", value заполняется
- `price` + `volume` → main row с Price + кнопка "Add condition" → sub-dialog с source="Vol" → внутри типится value → "Apply" → "Create"

**Ключевые DOM-классы:**
- Main dialog: `.dialog-qyCw0PaN`
- Sub-dialog (Add condition): `.conditionPopup-n3DR6Ngd` (это `.dialog-qyCw0PaN` с position:fixed — `offsetParent === null` даже когда видим, поэтому visible() должен проверять offsetWidth/Height и computed style)
- Кнопка "Add condition": `button` с textContent === "add condition"
- Source combo: span с `role="button"` внутри `.select-VfhgWFqC`
- Список источников: span.label-VfhgWFqC по точному тексту ("Vol", "Price", "EMA (63, close)", etc.)
- Список условий: `[class*="button-fOp9u5tE"]` — изначально показано Crossing/Up/Down + кнопка "Show more" (`.title-G9CradYu` с текстом `Show more`) разворачивает Greater Than, Less Than, Entering/Exiting/Inside/Outside Channel, Moving Up/Down/%.
- Sub-dialog кнопка коммита: "Add" (для нового условия) или "Apply" (для редактирования существующего).

**Why (важно):** React-controlled inputs внутри alert dialog НЕ принимают значения через:
- `document.execCommand('insertText', ...)` — DOM меняется, React state нет → при коммите ревертится к initial value (current market price для price-инпута, current volume для volume-инпута)
- Native setter `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set` + dispatchEvent('input') — то же самое, React state не подхватывает

**Что работает:** реальный CDP mouse-click по координатам инпута (triple-click для select) → `Input.dispatchKeyEvent` Cmd+A + Delete → `Input.insertText` → ручной dispatch 'input'/'change' event → CDP keystroke `Tab` для коммита. Без всех этих шагов значение не сохраняется.

**How to apply:**
- Простой price-алерт: `mcp__tradingview__alert_create({ price: 63 })`.
- Алерт >$X: `mcp__tradingview__alert_create({ price: 63, price_condition: "Greater Than" })`.
- Volume-only: `mcp__tradingview__alert_create({ volume: 5900000, volume_condition: "Crossing Up" })`.
- Multi-condition price + volume: `mcp__tradingview__alert_create({ price: 63, volume: 5900000, price_condition: "Greater Than", volume_condition: "Crossing Up" })` — создаст ОДИН алерт с message типа `"SYMBOL Greater Than 63.00 AND Volume Crossing Up 5.9 M on SYMBOL, 1D"` и condition.type="greater" в REST API.
- Volume поддерживает ТОЛЬКО Crossing/Crossing Up/Crossing Down — нет Greater Than. Семантика "volume >= X" эквивалентна "Crossing Up X".

**Проверка успеха:** в ответе `dialog_summary` должен содержать ожидаемые значения ДО клика Create. Также `created_alert.message` после создания.

**Удаление мусорных алертов** (REST endpoints `/remove_alert` etc. отдают `no_such_endpoint`; `alert_delete delete_all=true` снесёт ВСЕ алерты пользователя — опасно): через UI —
1. `mcp__tradingview__ui_open_panel(panel="alerts", action="open")`.
2. Переключиться на вкладку Alerts (не Log) если требуется.
3. На каждый удаляемый — найти `[data-name="alert-item-description"]`, подняться до родителя с `[data-name="alert-delete-button"]`, кликнуть.
4. Confirm dialog → `button` с текстом `Delete`.
5. sleep ~0.8s между алертами.

**Важное замечание про сервер:** после изменений в `src/core/alerts.js` MCP-сервер не подхватит код без рестарта (Node ESM-кеш). Тестировать можно через прямой запуск Node-скрипта импортирующего core/alerts.js — CDP-соединение singleton переподключится автоматически.
