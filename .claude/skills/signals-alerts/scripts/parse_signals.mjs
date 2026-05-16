#!/usr/bin/env node
/**
 * parse_signals.mjs — парсер `results/analysis/signals.md`.
 *
 * Выход: JSON-объект { signals: [...], skipped: [...] } в stdout.
 * Для каждого валидного сигнала формирует "alerts" — массив из 5 алертов
 * приоритетного сценария (Trigger / Stop / T1 / T2 / T3) с готовыми
 * полями `price`, `price_condition`, `message`. Это и есть «параметры»
 * для скрипта create_alerts.mjs.
 *
 * CLI:
 *   node parse_signals.mjs [--input results/analysis/signals.md]
 *                          [--tickers BSX,LULU,...]
 *
 * Тикеры в --tickers матчатся case-insensitive.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../../../..');
const DEFAULT_INPUT = path.join(REPO_ROOT, 'results/analysis/signals.md');

function parseArgs(argv) {
  const out = { input: DEFAULT_INPUT, tickers: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input' || a === '-i') out.input = argv[++i];
    else if (a === '--tickers' || a === '-t') {
      out.tickers = argv[++i].split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    } else if (a === '--help' || a === '-h') {
      console.log('Usage: parse_signals.mjs [--input PATH] [--tickers BSX,LULU]');
      process.exit(0);
    }
  }
  return out;
}

const fmtPrice = (n) => {
  if (n == null) return null;
  const fixed = n.toFixed(2);
  return fixed.replace(/\.00$/, '.00');
};

function firstDollarNumber(s) {
  if (!s) return null;
  const m = s.match(/\$\s*(\d+(?:\.\d+)?)/);
  if (m) return parseFloat(m[1]);
  const n = s.match(/(\d+(?:\.\d+)?)/);
  return n ? parseFloat(n[1]) : null;
}

function allDollarNumbers(s) {
  if (!s) return [];
  const out = [];
  const re = /\$\s*(\d+(?:\.\d+)?)/g;
  let m;
  while ((m = re.exec(s))) out.push(parseFloat(m[1]));
  if (out.length === 0) {
    const re2 = /(\d+(?:\.\d+)?)/g;
    while ((m = re2.exec(s))) out.push(parseFloat(m[1]));
  }
  return out;
}

function parseBlock(block) {
  const lines = block.split('\n');
  const headerLine = lines.find((l) => /^##\s+\d{4}-\d{2}-\d{2}\s*[—\-]/.test(l));
  if (!headerLine) return null;

  const headerMatch = headerLine.match(/^##\s+(\d{4}-\d{2}-\d{2})\s*[—\-]\s*([A-Z][A-Z0-9.\-]*)\s*[—\-]\s*(.*)$/);
  if (!headerMatch) return null;

  const [, date, ticker, statusText] = headerMatch;

  if (/\bno trade\b/i.test(statusText) || /\(сигнала нет\)/i.test(statusText)) {
    return { ticker, date, skip: true, reason: 'нет приоритетного сетапа (заголовок)' };
  }

  let direction = null;
  if (/🟢\s*BUY/.test(statusText)) direction = 'LONG';
  else if (/🔴\s*SELL/.test(statusText)) direction = 'SHORT';

  let triggerLine = null;
  let triggerDirection = null;
  for (const l of lines) {
    const m = l.match(/\*\*Trigger\s+(?:для\s+)?(Long|Short)\b[^:]*:\*\*\s*(.+)$/i);
    if (m) {
      triggerLine = m[2];
      triggerDirection = m[1].toUpperCase() === 'LONG' ? 'LONG' : 'SHORT';
      break;
    }
  }

  if (!triggerLine) {
    return { ticker, date, skip: true, reason: 'нет строки Trigger' };
  }
  if (!direction) direction = triggerDirection;

  const trigger = firstDollarNumber(triggerLine);

  let stop = null;
  for (const l of lines) {
    if (/Альтернатив[ау]/i.test(l)) continue;
    const m = l.match(/\*\*Stop:\*\*\s*(.+)$/i);
    if (m) {
      stop = firstDollarNumber(m[1]);
      break;
    }
  }

  let t1 = null, t2 = null, t3 = null;
  for (const l of lines) {
    if (/Альтернатив[ау]/i.test(l)) continue;
    const m = l.match(/\*\*T1(?:\s*\/\s*T2)?(?:\s*\/\s*T3)?:\*\*\s*(.+)$/i);
    if (m) {
      const nums = allDollarNumbers(m[1]);
      t1 = nums[0] ?? null;
      t2 = nums[1] ?? null;
      t3 = nums[2] ?? null;
      break;
    }
  }

  if (trigger == null || stop == null || t1 == null) {
    return { ticker, date, skip: true, reason: `неполные уровни (trigger=${trigger}, stop=${stop}, t1=${t1})` };
  }

  return { ticker, date, direction, trigger, stop, t1, t2, t3, skip: false };
}

function buildAlerts(sig) {
  const isLong = sig.direction === 'LONG';
  const dirRu = isLong ? 'лонг' : 'шорт';
  const upDir = isLong ? 'Crossing Up' : 'Crossing Down';
  const downDir = isLong ? 'Crossing Down' : 'Crossing Up';
  const buySell = isLong ? 'покупку' : 'продажу';

  const fmt = (n) => fmtPrice(n);
  const out = [
    {
      level: 'Trigger',
      price: sig.trigger,
      price_condition: upDir,
      message: `${sig.ticker}: сигнал на ${buySell} (${dirRu}) — Trigger $${fmt(sig.trigger)}`,
    },
    {
      level: 'Stop',
      price: sig.stop,
      price_condition: downDir,
      message: `${sig.ticker}: закрытие позиции по стопу (${dirRu}) — Stop $${fmt(sig.stop)}`,
    },
    {
      level: 'T1',
      price: sig.t1,
      price_condition: upDir,
      message: `${sig.ticker}: закрытие позиции по T1 (${dirRu}) — $${fmt(sig.t1)}`,
    },
  ];
  if (sig.t2 != null) {
    out.push({
      level: 'T2',
      price: sig.t2,
      price_condition: upDir,
      message: `${sig.ticker}: закрытие позиции по T2 (${dirRu}) — $${fmt(sig.t2)}`,
    });
  }
  if (sig.t3 != null) {
    out.push({
      level: 'T3',
      price: sig.t3,
      price_condition: upDir,
      message: `${sig.ticker}: закрытие позиции по T3 (${dirRu}) — $${fmt(sig.t3)}`,
    });
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const raw = fs.readFileSync(args.input, 'utf8');

  const blocks = raw.split(/\n\s*---\s*\n/);
  const signals = [];
  const skipped = [];

  for (const block of blocks) {
    const parsed = parseBlock(block);
    if (!parsed) continue;
    if (args.tickers && !args.tickers.includes(parsed.ticker.toUpperCase())) continue;

    if (parsed.skip) {
      skipped.push({ ticker: parsed.ticker, date: parsed.date, reason: parsed.reason });
      continue;
    }

    signals.push({
      ticker: parsed.ticker,
      date: parsed.date,
      direction: parsed.direction,
      trigger: parsed.trigger,
      stop: parsed.stop,
      t1: parsed.t1,
      t2: parsed.t2,
      t3: parsed.t3,
      alerts: buildAlerts(parsed),
    });
  }

  process.stdout.write(JSON.stringify({ signals, skipped, source: args.input }, null, 2) + '\n');
}

main();
