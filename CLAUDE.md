# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

MCP bridge between Claude Code and a locally running TradingView Desktop app, talking via Chrome DevTools Protocol on `localhost:9222`. Ships 81 MCP tools (`mcp__tradingview__*`) and a mirror `tv` CLI.

## Common commands

```bash
npm install                  # install deps (Node 18+)
npm start                    # run the MCP server over stdio (used by Claude Code via .mcp.json)
npm link                     # install the `tv` CLI globally — required to use `tv ...` from anywhere
tv brief                     # the canonical end-to-end smoke test; needs TradingView running with CDP

npm test                     # e2e + pine_analyze suites (default CI gate)
npm run test:all             # adds CLI tests
npm run test:unit            # offline-only suites (pine_analyze + cli, no TradingView needed)
npm run test:cli             # CLI router/command tests only
npm run test:verbose         # spec reporter for debugging a failing test
node --test tests/e2e.test.js --test-name-pattern='<name>'   # run a single test by name
node --test --test-only tests/<file>                          # run only test()s marked `only: true`

npm run format               # prettier write
npm run format:check         # prettier check (CI)
```

E2E tests require a live TradingView Desktop with CDP enabled (`./scripts/launch_tv_debug_mac.sh` or `tv_launch` MCP tool). `pine_analyze` and `cli` suites are pure unit tests and run anywhere.

## Architecture

Three layers, all ESM, zero build step:

1. **`src/connection.js`** — singleton CDP client. `getClient()` returns a live, lazily-reconnecting client; `evaluate(expr)` / `evaluateAsync(expr)` run JS inside the TradingView page. `KNOWN_PATHS` holds the discovered internal API entry points (`window.TradingViewApi._activeChartWidgetWV.value()` etc.) — these were found by live probing and are how every feature ultimately reaches into TradingView.
2. **`src/core/*.js`** — pure logic modules (`chart`, `data`, `pine`, `replay`, `morning`, …). Each exports plain async functions that build a JS expression, hand it to `evaluate()`, and shape the response. These are the canonical implementations and are also re-exported from `src/core/index.js` as `tradingview-mcp/core`.
3. **`src/tools/*.js`** — thin `register*Tools(server)` adapters that wrap each core function as an MCP tool with a Zod schema, formatted via `_format.js#jsonResult`. `src/server.js` boots `McpServer` (stdio transport) and calls every `register*` once. The big `instructions:` block on the server is the in-protocol tool-selection guide that ships to the client.

The `tv` CLI (`src/cli/index.js` → `src/cli/router.js` → `src/cli/commands/*.js`) is a parallel surface that calls the same `src/core` functions — never re-implement logic in commands; route through core.

**Adding a new tool**: write the function in `src/core/<group>.js`, register it in `src/tools/<group>.js` with a Zod schema, add a CLI command in `src/cli/commands/<group>.js` that imports the same core function, and (if it's part of the public API) re-export from `src/core/index.js`.

### Extra subsystems

- **Morning brief** (`src/core/morning.js` + `src/tools/morning.js`): reads `rules.json` (user's watchlist + bias criteria), runs `batch_run` over the watchlist, and persists sessions under `~/.tradingview-mcp/sessions/YYYY-MM-DD.json`. `rules.example.json` is the schema reference.
- **Pine analyzer** (`src/core/pine.js`'s offline analyzer + `tests/pine_analyze.test.js`): static checks on Pine source without needing a live chart — that's why this suite is in the default `npm test`.
- **Metrics cache** (`scripts/collect_russell.js` + `scripts/lib/{indicators,metrics_store}.js`, reader `scripts/lib/metrics_cache.py`): a per-ticker on-disk cache under `state/metrics/TICKER/` — `metrics.json` (indicators computed locally from bars + TradingView fundamentals + price summary) and `ohlcv.json` (raw daily bars). The collector walks a universe (`state/russel2000.json` / `state/sp500.csv`) and writes the cache; **no external store — local files only** (resume/update is derived from `metrics.json`'s `collected_at`/`as_of_date`, merging bars on `--update`). Skills read it as a fast path before driving the chart — `node scripts/read_metrics.js TICKER` (exit 0 fresh ≤2 days, exit 3 stale/missing → live fetch) or the Python reader — and the screeners (`canslim`/`vcp`), `downtrend-duration-analyzer`, and `scripts/scan_reversals.py` all consume it. See the `metrics_cache_system` memory for the full contract.

## TradingView MCP tool usage

Detailed tool-selection decision tree, context-management rules, and per-tool output sizes live in `.claude/skills/tradingview-mcp/SKILL.md` (loaded on demand). Read that skill before invoking `mcp__tradingview__*` tools.

## Project rules (from `.claude/rules/`)

- **Язык**: всегда отвечай по-русски, не переключайся на украинский или другой язык без прямой просьбы.
- **Файлы**: временные → `./tmp/`, финальные результаты → `./results/`.

## Saving reports

All reports are saved to `./results/analysis/Tiker/Date`.


## Response language

Always respond in Russian.

