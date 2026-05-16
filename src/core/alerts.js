/**
 * Core alert logic.
 *
 * Multi-condition note: when both `price` and `volume` are supplied, the dialog
 * fills the main row with the price condition and then opens "Add condition"
 * sub-dialog to attach a volume condition (Crossing Up by default). The
 * sub-dialog's value field is a tightly-controlled React input — DOM
 * `execCommand('insertText')` and the native value setter both lose their
 * change on submit. The only reliable way is real CDP keystrokes via
 * `Input.insertText` after focusing the field.
 */
import { evaluate, getClient } from '../connection.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const VISIBLE_FN = `
  function visible(el){
    if (!el) return false;
    if (el.offsetWidth === 0 && el.offsetHeight === 0) return false;
    var cs = window.getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }
`;

const MAIN_DIALOG_SELECTOR = '.dialog-qyCw0PaN';
const SUB_DIALOG_SELECTOR = '.conditionPopup-n3DR6Ngd';

async function openAlertDialog() {
  const opened = await evaluate(`
    (function() {
      var btn = document.querySelector('[aria-label="Create Alert"]')
        || document.querySelector('[aria-label="Create alert"]')
        || document.querySelector('[data-name="alerts"]');
      if (btn) { btn.click(); return true; }
      return false;
    })()
  `);

  if (!opened) {
    const client = await getClient();
    await client.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 1, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65 });
    await client.Input.dispatchKeyEvent({ type: 'keyUp', key: 'a', code: 'KeyA' });
  }

  await sleep(1500);
  return !!opened;
}

async function getInputRect(dialogSelector) {
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${dialogSelector}')).filter(visible)[0];
      if (!dlg) return null;
      var inp = Array.from(dlg.querySelectorAll('input')).filter(visible)[0];
      if (!inp) return null;
      var r = inp.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, value: inp.value };
    })()
  `);
}

async function clickInputAt(x, y) {
  const c = await getClient();
  await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: 'left', clickCount: 2 });
  await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: 'left', clickCount: 2 });
  await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: 'left', clickCount: 3 });
  await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: 'left', clickCount: 3 });
}

async function typeIntoInput(dialogSelector, value) {
  const rect = await getInputRect(dialogSelector);
  if (!rect) return { ok: false, reason: 'no_input_rect' };
  await clickInputAt(rect.x, rect.y);
  await sleep(250);
  const focusCheck = await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${dialogSelector}')).filter(visible)[0];
      var inp = dlg ? Array.from(dlg.querySelectorAll('input')).filter(visible)[0] : null;
      return {
        active_is_input: document.activeElement === inp,
        active_tag: document.activeElement ? document.activeElement.tagName : null,
        active_class: document.activeElement ? (document.activeElement.className||'').toString().substring(0,80) : null,
        input_value: inp ? inp.value : null
      };
    })()
  `);
  const c = await getClient();
  await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 4, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 4, key: 'a', code: 'KeyA' });
  await sleep(50);
  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Delete', code: 'Delete' });
  await sleep(50);
  await c.Input.insertText({ text: String(value) });
  await sleep(200);
  await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${dialogSelector}')).filter(visible)[0];
      var inp = dlg ? Array.from(dlg.querySelectorAll('input')).filter(visible)[0] : null;
      if (!inp) return false;
      var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(inp, inp.value);
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()
  `);
  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Tab', code: 'Tab' });
  await sleep(200);
  const after = await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${dialogSelector}')).filter(visible)[0];
      var inp = dlg ? Array.from(dlg.querySelectorAll('input')).filter(visible)[0] : null;
      return { input_value: inp ? inp.value : null };
    })()
  `);
  return {
    ok: true,
    value_before: rect.value,
    focus_check: focusCheck,
    value_after: after?.input_value
  };
}

async function fillMainValueInput(value) {
  return await typeIntoInput(MAIN_DIALOG_SELECTOR, value);
}

async function selectMainSource(label) {
  const target = JSON.stringify(label);
  await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${MAIN_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return false;
      var combo = dlg.querySelector('[class*="select-VfhgWFqC"]');
      if (combo) { combo.click(); return true; }
      var spanBtn = dlg.querySelector('span[role="button"]');
      if (spanBtn) { spanBtn.click(); return true; }
      return false;
    })()
  `);
  await sleep(500);
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var target = ${target};
      var labels = Array.from(document.querySelectorAll('[class*="label-VfhgWFqC"]'))
        .filter(visible)
        .filter(function(el){ return (el.textContent||'').trim() === target; });
      if (!labels.length) {
        document.body.click();
        return { ok: false, reason: 'option_not_found' };
      }
      var p = labels[0].parentElement;
      while (p && !(p.className && /item/i.test(p.className.toString())) && p.tagName !== 'BUTTON' && p !== document.body) {
        p = p.parentElement;
      }
      (p || labels[0]).click();
      return { ok: true };
    })()
  `);
}

async function clickAddConditionButton() {
  const r = await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${MAIN_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return { ok: false, reason: 'no_dialog' };
      var btn = Array.from(dlg.querySelectorAll('button'))
        .filter(visible)
        .filter(function(b){ return /^add condition$/i.test((b.textContent||'').trim()); })[0];
      if (!btn) return { ok: false, reason: 'no_add_condition_btn' };
      btn.click();
      return { ok: true };
    })()
  `);
  if (r?.ok) await sleep(800);
  return r;
}

async function openSubDialogSourceCombo() {
  const r = await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${SUB_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return { ok: false, reason: 'no_sub_dialog' };
      var spanBtn = dlg.querySelector('span[role="button"]');
      if (!spanBtn) return { ok: false, reason: 'no_combo' };
      spanBtn.click();
      return { ok: true };
    })()
  `);
  if (r?.ok) await sleep(500);
  return r;
}

async function pickSourceOption(label) {
  const target = JSON.stringify(label);
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var target = ${target};
      var labels = Array.from(document.querySelectorAll('[class*="label-VfhgWFqC"]'))
        .filter(visible)
        .filter(function(el){ return (el.textContent||'').trim() === target; });
      if (!labels.length) return { ok: false, reason: 'option_not_found' };
      var p = labels[0].parentElement;
      while (p && !(p.className && /item/i.test(p.className.toString())) && p.tagName !== 'BUTTON' && p !== document.body) {
        p = p.parentElement;
      }
      (p || labels[0]).click();
      return { ok: true };
    })()
  `);
}

async function selectConditionInDialog(dialogSelector, condition) {
  if (!condition || /^crossing$/i.test(condition)) return { ok: true, skipped: true };
  await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${dialogSelector}')).filter(visible)[0];
      if (!dlg) return false;
      var btn = Array.from(dlg.querySelectorAll('button'))
        .filter(visible)
        .filter(function(b){ return /^crossing/i.test((b.textContent||'').trim()); })[0];
      if (btn) { btn.click(); return true; }
      return false;
    })()
  `);
  await sleep(400);
  const target = JSON.stringify(condition);
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var target = ${target};
      var sm = Array.from(document.querySelectorAll('.title-G9CradYu, .sectionTitle-PTVMorAu'))
        .filter(visible)
        .filter(function(el){ return /show more/i.test(el.textContent); })[0];
      if (sm) sm.click();
      var items = Array.from(document.querySelectorAll('[class*="button-fOp9u5tE"]'))
        .filter(visible);
      var match = items.filter(function(el){ return (el.textContent||'').trim().toLowerCase() === target.toLowerCase(); })[0];
      if (!match) {
        document.body.click();
        return { ok: false, reason: 'condition_not_found' };
      }
      match.click();
      return { ok: true };
    })()
  `);
}

async function fillSubDialogValueInput(value) {
  return await typeIntoInput(SUB_DIALOG_SELECTOR, value);
}

async function clickSubDialogApplyOrAdd() {
  const r = await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${SUB_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return { ok: false, reason: 'no_sub_dialog' };
      var btn = Array.from(dlg.querySelectorAll('button'))
        .filter(visible)
        .filter(function(b){ return /^(apply|add)$/i.test((b.textContent||'').trim()); })[0];
      if (!btn) return { ok: false, reason: 'no_apply_btn' };
      btn.click();
      return { ok: true };
    })()
  `);
  if (r?.ok) await sleep(600);
  return r;
}

async function readMainDialogSummary() {
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${MAIN_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return null;
      return (dlg.textContent || '').trim().substring(0, 500);
    })()
  `);
}

async function clickMainCreate() {
  return await evaluate(`
    (function() {
      ${VISIBLE_FN}
      var dlg = Array.from(document.querySelectorAll('${MAIN_DIALOG_SELECTOR}')).filter(visible)[0];
      if (!dlg) return { ok: false, reason: 'no_dialog' };
      var btn = Array.from(dlg.querySelectorAll('button'))
        .filter(visible)
        .filter(function(b){ return /^create$/i.test((b.textContent||'').trim()); })[0];
      if (!btn) return { ok: false, reason: 'no_create_btn' };
      btn.click();
      return { ok: true };
    })()
  `);
}

export async function create({ condition, price, volume, message, price_condition, volume_condition }) {
  if (price == null && volume == null) {
    throw new Error('Either "price" or "volume" must be provided.');
  }

  await openAlertDialog();

  const result = {
    price: price ?? null,
    volume: volume ?? null,
    price_condition: price_condition || null,
    volume_condition: volume_condition || null,
    condition: condition || (price != null && volume != null ? 'multi' : 'crossing'),
    steps: {},
  };

  if (price != null && volume == null) {
    if (price_condition) {
      result.steps.main_condition = await selectConditionInDialog(MAIN_DIALOG_SELECTOR, price_condition);
    }
    result.steps.main_price_filled = await fillMainValueInput(price);
  } else if (price == null && volume != null) {
    const sw = await selectMainSource('Vol');
    result.steps.main_source_switch = sw;
    await sleep(400);
    if (volume_condition) {
      result.steps.main_condition = await selectConditionInDialog(MAIN_DIALOG_SELECTOR, volume_condition);
    }
    result.steps.main_volume_typed = await fillMainValueInput(volume);
  } else {
    if (price_condition) {
      result.steps.main_condition = await selectConditionInDialog(MAIN_DIALOG_SELECTOR, price_condition);
    }
    result.steps.main_price_filled = await fillMainValueInput(price);
    const addRes = await clickAddConditionButton();
    result.steps.add_condition = addRes;
    if (addRes?.ok) {
      const openCombo = await openSubDialogSourceCombo();
      result.steps.sub_open_combo = openCombo;
      if (openCombo?.ok) {
        const pickRes = await pickSourceOption('Vol');
        result.steps.sub_pick_volume = pickRes;
        await sleep(400);
      }
      if (volume_condition) {
        result.steps.sub_condition = await selectConditionInDialog(SUB_DIALOG_SELECTOR, volume_condition);
      }
      result.steps.sub_volume_typed = await fillSubDialogValueInput(volume);
      const applyRes = await clickSubDialogApplyOrAdd();
      result.steps.sub_apply = applyRes;
    }
  }

  result.dialog_summary = await readMainDialogSummary();

  const createRes = await clickMainCreate();
  result.steps.main_create = createRes;
  await sleep(1200);

  // Detect success by looking up the freshest alert for this symbol.
  let createdAlert = null;
  try {
    const listed = await list();
    if (listed?.alerts?.length) {
      createdAlert = listed.alerts[0];
    }
  } catch {}

  if (message) {
    result.message_note = 'default dialog does not expose textarea — custom message ignored';
  }

  return {
    success: !!createRes?.ok,
    ...result,
    created_alert: createdAlert,
    source: 'dom_multi_condition',
  };
}

export async function list() {
  const result = await evaluate(`
    (async function() {
      try {
        var r = await fetch('https://pricealerts.tradingview.com/list_alerts', { credentials: 'include' });
        var data = await r.json();
        if (data.s !== 'ok' || !Array.isArray(data.r)) return { alerts: [], error: data.errmsg || 'Unexpected response' };
        return {
          alerts: data.r.map(function(a) {
            var sym = '';
            try { sym = JSON.parse(a.symbol.replace(/^=/, '')).symbol || a.symbol; } catch(e) { sym = a.symbol; }
            return {
              alert_id: a.alert_id,
              symbol: sym,
              type: a.type,
              message: a.message,
              active: a.active,
              condition: a.condition,
              resolution: a.resolution,
              created: a.create_time,
              last_fired: a.last_fire_time,
              expiration: a.expiration,
            };
          })
        };
      } catch (e) { return { alerts: [], error: String(e) }; }
    })()
  `, { awaitPromise: true });
  return { success: true, alert_count: result?.alerts?.length || 0, source: 'internal_api', alerts: result?.alerts || [], error: result?.error };
}

export async function deleteAlerts({ delete_all }) {
  if (delete_all) {
    const result = await evaluate(`
      (function() {
        var alertBtn = document.querySelector('[data-name="alerts"]');
        if (alertBtn) alertBtn.click();
        var header = document.querySelector('[data-name="alerts"]');
        if (header) {
          header.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: 100, clientY: 100 }));
          return { context_menu_opened: true };
        }
        return { context_menu_opened: false };
      })()
    `);
    return { success: true, note: 'Alert deletion requires manual confirmation in the context menu.', context_menu_opened: result?.context_menu_opened || false, source: 'dom_fallback' };
  }
  throw new Error('Individual alert deletion not yet supported. Use delete_all: true.');
}
