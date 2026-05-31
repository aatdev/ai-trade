#!/usr/bin/env node
/**
 * add_to_watchlist.mjs — добавляет список тикеров в ИМЕНОВАННЫЙ watchlist TradingView.
 *
 * Штатный `watchlist.add()` (src/core/watchlist.js) пишет только в АКТИВНЫЙ список.
 * Этот скрипт сначала переключается на нужный список по имени (по умолчанию "t"),
 * проверяет, что переключение реально произошло (читает заголовок), и только затем
 * добавляет тикеры — один CDP-сеанс на весь батч, без оверхеда на отдельные tool-calls.
 *
 * Безопасность: если список с таким именем не найден И не передан --create —
 * скрипт НЕ добавляет ничего (чтобы не засорять чужой активный список) и выходит с кодом 3.
 *
 * CLI:
 *   node add_to_watchlist.mjs --tickers NVDA,AVGO,PLTR            # в список "t"
 *   node add_to_watchlist.mjs --name "t" --tickers NVDA,AVGO      # явное имя
 *   echo '["NVDA","AVGO"]' | node add_to_watchlist.mjs            # тикеры из stdin (JSON-массив)
 *   node add_to_watchlist.mjs --tickers NVDA --create             # создать список, если его нет
 *   node add_to_watchlist.mjs --tickers NVDA --dry-run            # только проверить/переключить, не добавлять
 *
 * stdout: JSON-отчёт { watchlist, switched, created_list, added: [...], already: [...], errors: [...], summary }
 */
import fs from 'node:fs';
import { evaluate, getClient } from '../../../../src/connection.js';
import * as health from '../../../../src/core/health.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const out = { name: 't', tickers: [], create: false, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--name' || a === '-n') out.name = argv[++i];
    else if (a === '--tickers' || a === '-t') out.tickers = String(argv[++i] || '').split(/[,\s]+/).filter(Boolean);
    else if (a === '--create') out.create = true;
    else if (a === '--dry-run') out.dryRun = true;
  }
  return out;
}

function readStdinTickers() {
  try {
    const raw = fs.readFileSync(0, 'utf8').trim();
    if (!raw) return [];
    if (raw.startsWith('[')) return JSON.parse(raw).map(String);
    if (raw.startsWith('{')) {
      const obj = JSON.parse(raw);
      // допускаем {tickers:[...]} или {symbols:[...]} или {candidates:[{ticker}...]}
      if (Array.isArray(obj.tickers)) return obj.tickers.map(String);
      if (Array.isArray(obj.symbols)) return obj.symbols.map((s) => (typeof s === 'string' ? s : s.symbol || s.ticker)).filter(Boolean);
      if (Array.isArray(obj.candidates)) return obj.candidates.map((c) => c.ticker || c.symbol).filter(Boolean);
    }
    return raw.split(/[,\s]+/).filter(Boolean);
  } catch {
    return [];
  }
}

/** Открыть правую панель watchlist, если закрыта. */
async function ensurePanelOpen() {
  const st = await evaluate(`
    (function() {
      var btn = document.querySelector('[data-name="base-watchlist-widget-button"]')
        || document.querySelector('[aria-label*="Watchlist"]');
      if (!btn) return { error: 'Watchlist button not found' };
      var isActive = btn.getAttribute('aria-pressed') === 'true'
        || btn.classList.toString().toLowerCase().indexOf('active') !== -1;
      if (!isActive) { btn.click(); return { opened: true }; }
      return { opened: false };
    })()
  `);
  if (st?.error) throw new Error(st.error);
  if (st?.opened) await sleep(600);
}

/** Прочитать имя текущего (активного) watchlist из заголовка панели. */
async function readActiveName() {
  return await evaluate(`
    (function() {
      var sels = [
        '[data-name="watchlists-button"]',
        '[data-name="watchlist-title"]',
        '[class*="watchlistTitle"]',
        '[class*="title-"][class*="watchlist"]',
      ];
      for (var i = 0; i < sels.length; i++) {
        var el = document.querySelector(sels[i]);
        if (el && el.offsetParent !== null) {
          var t = (el.textContent || '').trim();
          if (t) return t;
        }
      }
      return null;
    })()
  `);
}

/**
 * Переключиться на watchlist с именем name. Возвращает { switched, created_list, active }.
 * Алгоритм: клик по селектору watchlist'ов → в выпавшем меню найти строку с точным текстом name → клик.
 * Если нет и create=true — пытается нажать «Create new watchlist» и ввести имя.
 */
async function selectWatchlist(name, { create }) {
  const c = await getClient();

  // Если уже активен нужный — ничего не делаем.
  const before = await readActiveName();
  if (before && before.trim().toLowerCase() === name.toLowerCase()) {
    return { switched: false, created_list: false, active: before, note: 'already_active' };
  }

  // Открыть выпадающий список сохранённых watchlist'ов.
  const opened = await evaluate(`
    (function() {
      var sels = [
        '[data-name="watchlists-button"]',
        '[data-name="watchlist-title"]',
        '[class*="watchlistTitle"]',
      ];
      for (var i = 0; i < sels.length; i++) {
        var el = document.querySelector(sels[i]);
        if (el && el.offsetParent !== null) { el.click(); return { clicked: sels[i] }; }
      }
      return { clicked: null };
    })()
  `);
  if (!opened?.clicked) {
    return { switched: false, created_list: false, active: before, error: 'Не найден переключатель watchlist (dropdown).' };
  }
  await sleep(500);

  // Найти и кликнуть пункт меню с точным именем.
  const picked = await evaluate(`
    (function(target) {
      var rows = document.querySelectorAll('[data-name="watchlists-dialog"] [role="row"], [data-name="watchlists-dialog"] [class*="item"], [role="dialog"] [class*="item"], [role="menu"] [role="menuitem"]');
      for (var i = 0; i < rows.length; i++) {
        var el = rows[i];
        if (el.offsetParent === null) continue;
        // имя списка обычно в отдельном span; берём первую непустую короткую строку
        var label = (el.querySelector('[class*="title"], [class*="name"]') || el).textContent.trim();
        if (label === target) {
          (el.querySelector('[class*="title"], [class*="name"]') || el).click();
          return { found: true, label: label };
        }
      }
      return { found: false };
    })(${JSON.stringify(name)})
  `);

  if (picked?.found) {
    await sleep(600);
    const active = await readActiveName();
    return { switched: true, created_list: false, active };
  }

  // Не нашли список. Создаём, если разрешено.
  if (!create) {
    // Закрыть меню Escape, ничего не трогаем.
    await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });
    return { switched: false, created_list: false, active: before, error: `Watchlist "${name}" не найден (передай --create, чтобы создать).` };
  }

  const createClicked = await evaluate(`
    (function() {
      var btns = document.querySelectorAll('[role="dialog"] *, [role="menu"] *, [data-name="watchlists-dialog"] *');
      for (var i = 0; i < btns.length; i++) {
        var el = btns[i];
        if (el.offsetParent === null) continue;
        var t = (el.textContent || '').trim().toLowerCase();
        if (t === 'create new list' || t === 'create new watchlist' || /создать.*спис/.test(t)) {
          el.click();
          return { found: true };
        }
      }
      return { found: false };
    })()
  `);
  if (!createClicked?.found) {
    return { switched: false, created_list: false, active: before, error: 'Кнопка «Create new watchlist» не найдена.' };
  }
  await sleep(500);
  await c.Input.insertText({ text: name });
  await sleep(300);
  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Enter', code: 'Enter' });
  await sleep(700);
  const active = await readActiveName();
  return { switched: true, created_list: true, active };
}

/** Прочитать тикеры, уже присутствующие в активном списке. */
async function readSymbols() {
  const r = await evaluate(`
    (function() {
      var out = [], seen = {};
      var container = document.querySelector('[class*="layout__area--right"]');
      if (!container) return out;
      var els = container.querySelectorAll('[data-symbol-full]');
      for (var i = 0; i < els.length; i++) {
        var sym = els[i].getAttribute('data-symbol-full');
        if (!sym || seen[sym]) continue;
        seen[sym] = true; out.push(sym);
      }
      return out;
    })()
  `);
  return Array.isArray(r) ? r : [];
}

/** Добавить один символ в АКТИВНЫЙ список (логика из src/core/watchlist.js add()). */
async function addOne(symbol) {
  const c = await getClient();
  const addClicked = await evaluate(`
    (function() {
      var selectors = ['[data-name="add-symbol-button"]','[aria-label="Add symbol"]','[aria-label*="Add symbol"]','button[class*="addSymbol"]'];
      for (var s = 0; s < selectors.length; s++) {
        var btn = document.querySelector(selectors[s]);
        if (btn && btn.offsetParent !== null) { btn.click(); return { found: true }; }
      }
      var container = document.querySelector('[class*="layout__area--right"]');
      if (container) {
        var buttons = container.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
          var al = buttons[i].getAttribute('aria-label') || '';
          if (/add.*symbol/i.test(al) || buttons[i].textContent.trim() === '+') { buttons[i].click(); return { found: true }; }
        }
      }
      return { found: false };
    })()
  `);
  if (!addClicked?.found) throw new Error('Кнопка «Add symbol» не найдена');
  await sleep(350);
  await c.Input.insertText({ text: symbol });
  await sleep(550);
  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Enter', code: 'Enter' });
  await sleep(350);
  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.tickers.length) args.tickers = readStdinTickers();
  args.tickers = [...new Set(args.tickers.map((t) => t.trim().toUpperCase()).filter(Boolean))];

  const hc = await health.healthCheck().catch((e) => ({ ok: false, error: String(e?.message || e) }));
  if (!hc?.success && !hc?.ok) {
    process.stdout.write(JSON.stringify({ error: 'TradingView Desktop недоступен. Запусти `tv launch` или `./scripts/launch_tv_debug_mac.sh`.', health: hc }, null, 2) + '\n');
    process.exit(2);
  }

  if (!args.tickers.length) {
    process.stdout.write(JSON.stringify({ error: 'Не переданы тикеры (--tickers или stdin).' }, null, 2) + '\n');
    process.exit(1);
  }

  await ensurePanelOpen();
  const sel = await selectWatchlist(args.name, { create: args.create });

  // Безопасность: не добавляем, если не подтвердили, что активен нужный список.
  const activeOk = sel.active && sel.active.trim().toLowerCase() === args.name.toLowerCase();
  if (!activeOk) {
    process.stdout.write(JSON.stringify({
      watchlist: args.name, switched: sel.switched, created_list: sel.created_list, active: sel.active,
      error: sel.error || `Активный список "${sel.active}" ≠ "${args.name}" — добавление отменено во избежание записи в чужой список.`,
      added: [], already: [], errors: [],
    }, null, 2) + '\n');
    process.exit(3);
  }

  if (args.dryRun) {
    process.stdout.write(JSON.stringify({
      watchlist: args.name, switched: sel.switched, created_list: sel.created_list, active: sel.active,
      dry_run: true, would_add: args.tickers, added: [], already: [], errors: [],
    }, null, 2) + '\n');
    process.exit(0);
  }

  const existing = (await readSymbols()).map((s) => s.toUpperCase());
  const added = [], already = [], errors = [];
  for (const t of args.tickers) {
    // дедуп по голому тикеру и по виду EXCHANGE:TICKER
    if (existing.some((e) => e === t || e.endsWith(':' + t))) { already.push(t); continue; }
    try {
      await addOne(t);
      added.push(t);
      await sleep(400);
    } catch (e) {
      errors.push({ ticker: t, error: String(e?.message || e) });
    }
  }

  const summary = { watchlist: args.name, requested: args.tickers.length, added: added.length, already: already.length, errors: errors.length };
  process.stdout.write(JSON.stringify({
    watchlist: args.name, switched: sel.switched, created_list: sel.created_list, active: sel.active,
    added, already, errors, summary,
  }, null, 2) + '\n');
  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(`Fatal: ${e?.stack || e}\n`);
  process.exit(1);
});
